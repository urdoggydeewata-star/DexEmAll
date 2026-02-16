# pvp/db_pool.py
"""
Thread-safe PostgreSQL connection pool for high-traffic scenarios.
Reuses connections via asyncpg pool.
"""
from __future__ import annotations

import os
import threading
import atexit
import asyncio
from typing import Optional, Any, Dict
from contextlib import contextmanager

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL or POSTGRES_DSN must be set. PostgreSQL only.")

# PostgreSQL: single long-lived worker loop + pool
_pg_worker_loop: Optional[Any] = None
_pg_worker_pool: Optional[Any] = None
_pg_worker_ready = threading.Event()
_pg_worker_started = False
_pg_worker_lock = threading.Lock()

_DEFAULT_POOL_SIZE = 5
_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", str(_DEFAULT_POOL_SIZE)))
_TIMEOUT = 60.0


class ConnectionPool:
    """PostgreSQL connection pool. Thread-safe via dedicated worker loop."""

    def __init__(self, pool_size: int = _POOL_SIZE, timeout: float = _TIMEOUT):
        self.pool_size = pool_size
        self.timeout = timeout
        self._lock = threading.Lock()
        self._initialized = False
        self._pg_pool: Optional[asyncpg.Pool] = None
        atexit.register(self.close_all)

    def _start_pg_worker_if_needed(self) -> None:
        global _pg_worker_started, _pg_worker_loop, _pg_worker_pool, _pg_worker_ready
        with _pg_worker_lock:
            if _pg_worker_started:
                return
            _pg_worker_started = True

        def _worker_main() -> None:
            global _pg_worker_loop, _pg_worker_pool, _pg_worker_ready
            import sys
            if sys.platform == "win32":
                try:
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                except Exception:
                    pass
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _pg_worker_loop = loop

            async def _create_pool() -> None:
                global _pg_worker_pool
                dsn = DATABASE_URL or ""
                is_managed = ":6432" in dsn or (os.getenv("GOOGLE_CLOUD_SQL_POOL") or "").lower() in ("1", "true", "yes")
                min_size = int(os.getenv("DB_POOL_MIN", 1))
                max_size = int(os.getenv("DB_POOL_MAX", os.getenv("DB_POOL_SIZE", "20")))
                if min_size > max_size:
                    min_size, max_size = max_size, min_size
                if is_managed:
                    max_size = int(os.getenv("DB_POOL_MAX", "5"))
                    kw = {"min_size": min_size, "max_size": max_size, "command_timeout": _TIMEOUT, "statement_cache_size": 0}
                else:
                    kw = {"min_size": min_size, "max_size": max_size, "command_timeout": _TIMEOUT}
                _pg_worker_pool = await asyncpg.create_pool(dsn, **kw)
                _pg_worker_ready.set()

            try:
                loop.run_until_complete(_create_pool())
                loop.run_forever()
            except Exception as e:
                print(f"[DB Pool] PG worker error: {e}")
            finally:
                _pg_worker_ready.set()

        t = threading.Thread(target=_worker_main, daemon=True, name="pvp_pg_worker")
        t.start()
        _pg_worker_ready.wait(timeout=30)
        if _pg_worker_pool is None:
            raise RuntimeError("Failed to create PostgreSQL pool (worker timeout)")

    def get_connection(self):
        """Get a connection wrapper (PostgreSQL)."""
        self._start_pg_worker_if_needed()
        self._initialized = True
        sticky = os.getenv("DB_STICKY_CONN", "1").lower() not in ("0", "false", "no")
        return PostgreSQLConnectionWrapper(self, sticky=sticky)

    def return_connection(self, conn) -> None:
        try:
            if hasattr(conn, "close"):
                conn.close()
        except Exception:
            pass

    @contextmanager
    def connection(self):
        conn = self.get_connection()
        try:
            yield conn
        finally:
            self.return_connection(conn)

    def close_all(self) -> None:
        global _pg_worker_pool
        with self._lock:
            if _pg_worker_pool is not None and _pg_worker_loop is not None:
                try:
                    fut = asyncio.run_coroutine_threadsafe(_pg_worker_pool.close(), _pg_worker_loop)
                    fut.result(timeout=10)
                except Exception:
                    pass
                _pg_worker_pool = None
            self._initialized = False


class PostgreSQLConnectionWrapper:
    """SQLite-like interface for PostgreSQL (sync API over async pool)."""

    def __init__(self, pool: ConnectionPool, sticky: bool = True):
        self._pool = pool
        self._sticky = sticky
        self._pinned = None
        if sticky:
            self._pinned = self._run_async(self._acquire_pinned())

    def _run_async(self, coro):
        loop = _pg_worker_loop
        if loop is None or _pg_worker_pool is None:
            raise RuntimeError("PostgreSQL worker not initialized")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)

    def execute(self, query: str, params: tuple = ()):
        if "?" in query:
            parts = query.split("?")
            new_query = parts[0]
            for i, part in enumerate(parts[1:], 1):
                new_query += f"${i}" + part
            query = new_query
        params_list = list(params)
        rows = self._run_async(self._execute_query(query, params_list))
        return PostgreSQLCursor(rows)

    async def _execute_query(self, query: str, params: list):
        pool = _pg_worker_pool
        if pool is None:
            raise RuntimeError("PostgreSQL pool not initialized")
        if self._pinned is not None:
            if query.strip().upper().startswith("SELECT"):
                return await self._pinned.fetch(query, *params)
            await self._pinned.execute(query, *params)
            return []
        async with pool.acquire() as conn:
            if query.strip().upper().startswith("SELECT"):
                return await conn.fetch(query, *params)
            await conn.execute(query, *params)
            return []

    async def _acquire_pinned(self):
        return await _pg_worker_pool.acquire()

    async def _release_pinned(self, conn):
        if _pg_worker_pool is not None:
            await _pg_worker_pool.release(conn)

    def commit(self):
        pass

    def close(self):
        if self._pinned is not None:
            try:
                self._run_async(self._release_pinned(self._pinned))
            finally:
                self._pinned = None


class PostgreSQLRow:
    def __init__(self, data):
        if hasattr(data, "keys"):
            data = dict(data)
        self.__dict__.update(data)
        self._values = list(self.__dict__.values())
        self._keys = list(self.__dict__.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            if 0 <= key < len(self._values):
                return self._values[key]
            raise IndexError(key)
        return self.__dict__[key]

    def get(self, key, default=None):
        return self.__dict__.get(key, default)

    def keys(self):
        return self.__dict__.keys()


class PostgreSQLCursor:
    def __init__(self, rows: list):
        self._rows = rows
        self._index = 0
        self.rowcount = len(rows)

    def fetchone(self):
        if self._index < len(self._rows):
            row = self._rows[self._index]
            self._index += 1
            return PostgreSQLRow(dict(row) if hasattr(row, "keys") else row)
        return None

    def fetchall(self):
        remaining = self._rows[self._index:]
        self._index = len(self._rows)
        return [PostgreSQLRow(dict(row) if hasattr(row, "keys") else row) for row in remaining]


_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        _pool = ConnectionPool()
        return _pool


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close_all()
            _pool = None


@contextmanager
def get_connection():
    pool = get_pool()
    with pool.connection() as conn:
        yield conn


def execute_query(query: str, params: tuple = ()):
    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return cursor.fetchall()


def execute_one(query: str, params: tuple = ()):
    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return cursor.fetchone()


def execute_write(query: str, params: tuple = ()) -> int:
    with get_connection() as conn:
        cursor = conn.execute(query, params)
        conn.commit()
        return cursor.rowcount


def get_pool_stats() -> Dict[str, Any]:
    pool = get_pool()
    return {
        "pool_size": pool.pool_size,
        "database": "PostgreSQL",
        "initialized": _pg_worker_pool is not None,
    }
