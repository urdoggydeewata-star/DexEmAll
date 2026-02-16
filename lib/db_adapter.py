"""
Postgres-only adapter (DexThemAll uses Supabase).

Import as:
    from lib.db_adapter import aiosqlite, DB_IS_POSTGRES
"""
from __future__ import annotations

import os

DB_IS_POSTGRES = True  # Always use Postgres

from . import pg_aiosqlite as aiosqlite  # type: ignore

__all__ = ["aiosqlite", "DB_IS_POSTGRES"]

