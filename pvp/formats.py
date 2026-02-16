# -----------------------------------------------------------------------------
# Database-driven PvP formats system
# - Reads format rules from pvp_formats and pvp_format_rules tables
# - Supports generation-specific rules for OU and Ubers formats
# - Provides API for team validation and format selection
# -----------------------------------------------------------------------------

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Any, Optional, List
from pathlib import Path

from .db_pool import get_connection

try:
    from lib import db_cache
except ImportError:
    db_cache = None

@dataclass(frozen=True)
class FormatRules:
    label: str
    gen: int
    rules: Dict[str, Any]

def _list_formats_from_cache() -> Optional[Dict[str, Dict[str, Any]]]:
    """Build list_formats-style dict from cached pvp_formats + pvp_format_rules. None on cache miss."""
    if not db_cache:
        return None
    fmts = db_cache.get_cached_pvp_formats()
    rules = db_cache.get_cached_pvp_format_rules()
    if not fmts or not rules:
        return None
    max_gen_by_key: Dict[str, int] = {}
    for r in rules:
        k = (r.get("format_key") or "").strip().lower()
        if not k:
            continue
        g = r.get("generation")
        if g is not None:
            max_gen_by_key[k] = max(max_gen_by_key.get(k, 0), int(g))
    out: Dict[str, Dict[str, Any]] = {}
    for f in fmts:
        k = (f.get("key") or "").strip().lower()
        if not k:
            continue
        max_gen = max_gen_by_key.get(k, 9)
        out[k] = {
            "label": f.get("name") or k,
            "description": f.get("description") or "",
            "gen": max_gen,
            "available_gens": list(range(1, max_gen + 1))
        }
    return out if out else None

async def list_formats() -> Dict[str, Dict[str, Any]]:
    """Return available formats with their default generation"""
    cached = _list_formats_from_cache()
    if cached is not None:
        return cached
    with get_connection() as conn:
        cur = conn.execute("""
            SELECT f.key, f.name, f.description,
                   MAX(r.generation) as max_gen
            FROM pvp_formats f
            LEFT JOIN pvp_format_rules r ON f.key = r.format_key
            GROUP BY f.key, f.name, f.description
        """)
        formats = {}
        for row in cur.fetchall():
            formats[row["key"]] = {
                "label": row["name"],
                "description": row["description"],
                "gen": row["max_gen"] or 9,
                "available_gens": list(range(1, (row["max_gen"] or 9) + 1))
            }
        return formats

def _get_format_from_cache(fmt_key: str, gen: Optional[int]) -> Optional[FormatRules]:
    """Build FormatRules from cache. None on cache miss."""
    if not db_cache:
        return None
    fmts = db_cache.get_cached_pvp_formats()
    rules_list = db_cache.get_cached_pvp_format_rules()
    if not fmts or not rules_list:
        return None
    key = fmt_key.strip().lower()
    format_name = None
    for f in fmts:
        if (f.get("key") or "").strip().lower() == key:
            format_name = f.get("name") or key
            break
    if not format_name:
        key = "ou"
        for f in fmts:
            if (f.get("key") or "").strip().lower() == "ou":
                format_name = f.get("name") or "ou"
                break
        if not format_name:
            return None
    matching = [r for r in rules_list if (r.get("format_key") or "").strip().lower() == key]
    if not matching:
        return None
    if gen is None:
        gen = max(int(r.get("generation") or 0) for r in matching)
    rules_row = next((r for r in matching if int(r.get("generation") or 0) == gen), None)
    if not rules_row:
        by_gen = sorted(matching, key=lambda r: int(r.get("generation") or 0), reverse=True)
        rules_row = by_gen[0] if by_gen else None
    if not rules_row:
        return None
    def _j(s, d):
        if s is None or s == "":
            return d
        try:
            return json.loads(s) if isinstance(s, str) else s
        except Exception:
            return d
    rules = {
        "max_mon_gen": rules_row.get("max_mon_gen", 9),
        "clauses": _j(rules_row.get("clauses"), {}),
        "species_bans": _j(rules_row.get("species_bans"), []),
        "ability_bans": _j(rules_row.get("ability_bans"), []),
        "move_bans": _j(rules_row.get("move_bans"), []),
        "item_bans": _j(rules_row.get("item_bans"), []),
        "team_combo_bans": _j(rules_row.get("team_combo_bans"), []),
        "mon_combo_bans": _j(rules_row.get("mon_combo_bans"), []),
    }
    return FormatRules(label=format_name, gen=int(rules_row.get("generation") or gen or 9), rules=rules)

async def get_format(fmt_key: str, gen: Optional[int] = None) -> FormatRules:
    """
    Get format rules for a specific format and generation.
    If gen is None, uses the highest available generation for that format.
    """
    cached = _get_format_from_cache(fmt_key, gen)
    if cached is not None:
        return cached
    with get_connection() as conn:
        cur = conn.execute("SELECT name FROM pvp_formats WHERE key = ?", (fmt_key.lower(),))
        format_row = cur.fetchone()
        if not format_row:
            fmt_key = "ou"
            cur = conn.execute("SELECT name FROM pvp_formats WHERE key = ?", (fmt_key,))
            format_row = cur.fetchone()
        format_name = format_row["name"]
        if gen is None:
            cur = conn.execute("""
                SELECT MAX(generation) as max_gen 
                FROM pvp_format_rules 
                WHERE format_key = ?
            """, (fmt_key,))
            max_gen_row = cur.fetchone()
            gen = max_gen_row["max_gen"] or 9
        cur = conn.execute("""
            SELECT * FROM pvp_format_rules 
            WHERE format_key = ? AND generation = ?
        """, (fmt_key, gen))
        rules_row = cur.fetchone()
        if not rules_row:
            cur = conn.execute("""
                SELECT * FROM pvp_format_rules 
                WHERE format_key = ? 
                ORDER BY generation DESC 
                LIMIT 1
            """, (fmt_key,))
            rules_row = cur.fetchone()
        if not rules_row:
            raise ValueError(f"No rules found for format {fmt_key}")
        rules = {
            "max_mon_gen": rules_row["max_mon_gen"],
            "clauses": json.loads(rules_row["clauses"] or "{}"),
            "species_bans": json.loads(rules_row["species_bans"] or "[]"),
            "ability_bans": json.loads(rules_row["ability_bans"] or "[]"),
            "move_bans": json.loads(rules_row["move_bans"] or "[]"),
            "item_bans": json.loads(rules_row["item_bans"] or "[]"),
            "team_combo_bans": json.loads(rules_row["team_combo_bans"] or "[]"),
            "mon_combo_bans": json.loads(rules_row["mon_combo_bans"] or "[]")
        }
        return FormatRules(label=format_name, gen=rules_row["generation"], rules=rules)

def _get_available_generations_from_cache(fmt_key: str) -> Optional[List[int]]:
    if not db_cache:
        return None
    rules_list = db_cache.get_cached_pvp_format_rules()
    if not rules_list:
        return None
    key = fmt_key.strip().lower()
    gens = [int(r["generation"]) for r in rules_list if (r.get("format_key") or "").strip().lower() == key and r.get("generation") is not None]
    return sorted(set(gens)) if gens else None

async def get_available_generations(fmt_key: str) -> List[int]:
    """Get list of available generations for a format"""
    cached = _get_available_generations_from_cache(fmt_key)
    if cached is not None:
        return cached
    with get_connection() as conn:
        cur = conn.execute("""
            SELECT generation FROM pvp_format_rules 
            WHERE format_key = ? 
            ORDER BY generation
        """, (fmt_key.lower(),))
        return [row["generation"] for row in cur.fetchall()]

def max_allowed_mon_gen(rules: Dict[str, Any]) -> int:
    """Get maximum allowed Pokémon generation from rules"""
    return int(rules.get("max_mon_gen", 9))

def _default_gen(fmt_key: str) -> int:
    """Get default generation for a format (highest available)"""
    cached = _get_available_generations_from_cache(fmt_key)
    if cached:
        return max(cached)
    with get_connection() as conn:
        cur = conn.execute("""
            SELECT MAX(generation) as max_gen 
            FROM pvp_format_rules 
            WHERE format_key = ?
        """, (fmt_key.lower(),))
        row = cur.fetchone()
        return row["max_gen"] or 9