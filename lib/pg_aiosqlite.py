"""AsyncPG-backed compatibility shim for the aiosqlite API.

This lets the existing codebase keep using the familiar `aiosqlite.connect`
pattern while the underlying database is PostgreSQL. It supports:
- connect()/execute()/executescript()/commit()/close()
- Cursor with fetchone()/fetchall(), rowcount, and lastrowid (when available)
- Basic translation of SQLiteisms: ? placeholders -> $1, ON CONFLICT DO NOTHING,
  PRAGMA is ignored.
"""
from __future__ import annotations

import asyncio
import contextvars
import os
import re
from contextlib import asynccontextmanager
from typing import Any, Iterable, List, Optional, Sequence

import asyncpg

# Pool is created lazily
_pool: Optional[asyncpg.pool.Pool] = None
_pool_lock = asyncio.Lock()
_session_conn: contextvars.ContextVar[Optional[asyncpg.Connection]] = contextvars.ContextVar(
    "pg_session_conn",
    default=None,
)

# Expose Row alias for compatibility
Row = asyncpg.Record


def _dsn() -> str:
    return os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN") or "postgresql://postgres:postgres@localhost:5432/myuu"


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _convert_qmarks_to_dollars(sql: str) -> str:
    """Replace ? placeholders with $1, $2, ... while respecting quoted strings."""
    out = []
    idx = 1
    in_single = False
    in_double = False
    escape = False
    for ch in sql:
        if escape:
            out.append(ch)
            escape = False
            continue
        if ch == "\\":
            out.append(ch)
            escape = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            continue
        if ch == "?" and not in_single and not in_double:
            out.append(f"${idx}")
            idx += 1
        else:
            out.append(ch)
    return "".join(out)


def _rewrite_insert_or_ignore(sql: str) -> str:
    if not sql.lower().startswith("insert or ignore into"):
        return sql
    return re.sub(r"(?i)^insert or ignore into", "INSERT INTO", sql.strip()) + " ON CONFLICT DO NOTHING"


def _should_return_rows(sql_upper: str) -> bool:
    return sql_upper.startswith("SELECT") or "RETURNING" in sql_upper


def _parse_rowcount(status: str) -> int:
    # asyncpg returns e.g. "INSERT 0 1", "UPDATE 3", "DELETE 0"
    parts = status.split()
    for part in reversed(parts):
        if part.isdigit():
            return int(part)
    return 0


class Cursor:
    def __init__(self, rows: List[Row], lastrowid: Optional[int], rowcount: int):
        self._rows = rows or []
        self.lastrowid = lastrowid
        self.rowcount = rowcount
        self._idx = 0

    async def fetchone(self):
        if self._idx < len(self._rows):
            row = self._rows[self._idx]
            self._idx += 1
            return row
        return None

    async def fetchall(self):
        # Return remaining rows
        if self._idx == 0:
            self._idx = len(self._rows)
            return list(self._rows)
        remaining = self._rows[self._idx :]
        self._idx = len(self._rows)
        return remaining

    async def close(self):
        # Nothing to close; compatibility no-op
        return None


async def _get_pool() -> asyncpg.pool.Pool:
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            # Check if using Google Cloud SQL managed pool (port 6432 = pgbouncer)
            dsn = _dsn()
            is_managed_pool = ":6432" in dsn or os.getenv("GOOGLE_CLOUD_SQL_POOL", "").lower() in ("1", "true", "yes")

            min_size = _get_int("DB_POOL_MIN", 1)
            max_size = _get_int("DB_POOL_MAX", _get_int("DB_POOL_SIZE", 20))
            if min_size > max_size:
                min_size, max_size = max_size, min_size

            if is_managed_pool:
                # pgbouncer/managed pool: keep prepared statements off and default to tiny pool.
                min_size = _get_int("DB_POOL_MIN", 1)
                max_size = _get_int("DB_POOL_MAX", 5)
                pool_kwargs = {
                    "dsn": dsn,
                    "min_size": min_size,
                    "max_size": max_size,
                    "command_timeout": _get_int("DB_COMMAND_TIMEOUT", 120),
                    "statement_cache_size": 0,  # Required for pgbouncer - doesn't support prepared statements
                }
            else:
                # Direct PostgreSQL connection - use application-level pooling
                pool_kwargs = {
                    "dsn": dsn,
                    "min_size": min_size,
                    "max_size": max_size,
                    "command_timeout": _get_int("DB_COMMAND_TIMEOUT", 120),
                    "max_queries": _get_int("DB_POOL_MAX_QUERIES", 50000),
                    "max_inactive_connection_lifetime": float(os.getenv("DB_POOL_MAX_IDLE", "300.0")),
                }
                stmt_cache = _get_int("DB_STATEMENT_CACHE", 100)
                if stmt_cache >= 0:
                    pool_kwargs["statement_cache_size"] = stmt_cache

            connect_timeout = _get_float("DB_CONNECT_TIMEOUT", 15.0)
            _pool = await asyncpg.create_pool(**pool_kwargs, timeout=connect_timeout)
    return _pool


async def warm_pool(n: Optional[int] = None) -> int:
    """Warm the pool by acquiring/releasing up to n connections."""
    pool = await _get_pool()
    target = n if n is not None else pool._minsize  # type: ignore[attr-defined]
    target = max(1, int(target))
    conns: List[asyncpg.Connection] = []
    try:
        for _ in range(target):
            conns.append(await pool.acquire())
    finally:
        for c in conns:
            await pool.release(c)
    return target


async def _execute_with_conn(conn: asyncpg.Connection, sql: str, params: Sequence[Any] | None) -> Cursor:
    sql = sql.strip()
    if not sql:
        return Cursor([], None, 0)

    # Ignore pragmas (SQLite-only)
    if sql.upper().startswith("PRAGMA"):
        return Cursor([], None, 0)

    sql = _rewrite_insert_or_ignore(sql)
    sql = _convert_qmarks_to_dollars(sql)
    params = tuple(params or ())
    sql_upper = sql.upper()

    # Auto-return inserted rows to supply lastrowid when needed
    lastrowid: Optional[int] = None

    if sql_upper.startswith("INSERT") and "RETURNING" not in sql_upper:
        # Append RETURNING * before any trailing semicolon so PostgreSQL gets one valid statement
        base = sql.rstrip()
        if base.endswith(";"):
            base = base[:-1].rstrip()
        sql_with_returning = base + " RETURNING *"
        rows = await conn.fetch(sql_with_returning, *params)
        if rows and "id" in rows[0]:
            lastrowid = rows[0]["id"]
        return Cursor(list(rows), lastrowid, len(rows))

    if _should_return_rows(sql_upper):
        rows = await conn.fetch(sql, *params)
        if rows and "id" in rows[0]:
            lastrowid = rows[0]["id"]
        return Cursor(list(rows), lastrowid, len(rows))

    status = await conn.execute(sql, *params)
    return Cursor([], None, _parse_rowcount(status))


class Connection:
    """Lightweight connection facade that can pin a pool connection for its lifetime."""

    def __init__(self, pool: asyncpg.pool.Pool, pinned: Optional[asyncpg.Connection] = None):
        self._pool = pool
        self._pinned = pinned
        self.row_factory = Row  # compatibility shim

    async def execute(self, sql: str, params: Iterable[Any] | None = None) -> Cursor:
        # Reuse an existing session connection if available
        sess_conn = _session_conn.get()
        if sess_conn is not None:
            return await _execute_with_conn(sess_conn, sql, params)

        # Use pinned connection if available
        if self._pinned is not None:
            return await _execute_with_conn(self._pinned, sql, params)

        # Otherwise, borrow a pool connection for this query
        pool = await _get_pool()
        acquire_timeout = _get_float("DB_POOL_ACQUIRE_TIMEOUT", 10.0)
        conn = await pool.acquire(timeout=acquire_timeout)
        try:
            return await _execute_with_conn(conn, sql, params)
        finally:
            await pool.release(conn)

    async def execute_fetchone(self, sql: str, params: Iterable[Any] | None = None) -> Optional[Row]:
        """Compatibility: execute SELECT and return first row (like aiosqlite)."""
        cur = await self.execute(sql, params)
        try:
            return await cur.fetchone()
        finally:
            await cur.close()

    async def execute_fetchall(self, sql: str, params: Iterable[Any] | None = None) -> List[Row]:
        """Compatibility: execute SELECT and return all rows (like aiosqlite)."""
        cur = await self.execute(sql, params)
        try:
            return await cur.fetchall()
        finally:
            await cur.close()

    async def executescript(self, script: str) -> None:
        # naive split on ';' but respects basic SQL scripts in this repo
        statements = [stmt.strip() for stmt in script.split(";") if stmt.strip()]
        sess_conn = _session_conn.get()
        if sess_conn is not None:
            for stmt in statements:
                await _execute_with_conn(sess_conn, stmt, ())
            return
        if self._pinned is not None:
            for stmt in statements:
                await _execute_with_conn(self._pinned, stmt, ())
            return
        pool = await _get_pool()
        acquire_timeout = _get_float("DB_POOL_ACQUIRE_TIMEOUT", 10.0)
        async with pool.acquire(timeout=acquire_timeout) as conn:
            for stmt in statements:
                await _execute_with_conn(conn, stmt, ())

    async def commit(self) -> None:
        # Using autocommit via pool connections
        return None

    async def close(self) -> None:
        # Release pinned connection if present
        if self._pinned is not None:
            try:
                await self._pool.release(self._pinned)
            finally:
                self._pinned = None
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
        return False


async def connect(_: str | None = None, timeout: float | None = None) -> Connection:
    pool = await _get_pool()
    sticky = os.getenv("DB_STICKY_CONN", "1").lower() not in ("0", "false", "no")
    acquire_timeout = _get_float("DB_POOL_ACQUIRE_TIMEOUT", 10.0)
    if sticky:
        conn = await pool.acquire(timeout=acquire_timeout)
        return Connection(pool, pinned=conn)
    return Connection(pool)


@asynccontextmanager
async def session() -> Connection:
    """Reuse a single connection for multiple queries within this async context."""
    existing = _session_conn.get()
    if existing is not None:
        pool = await _get_pool()
        yield Connection(pool)
        return

    pool = await _get_pool()
    acquire_timeout = _get_float("DB_POOL_ACQUIRE_TIMEOUT", 10.0)
    conn = await pool.acquire(timeout=acquire_timeout)
    token = _session_conn.set(conn)
    try:
        yield Connection(pool)
    finally:
        _session_conn.reset(token)
        await pool.release(conn)
