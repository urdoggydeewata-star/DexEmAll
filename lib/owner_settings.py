from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _to_int_set(value: Any) -> set[int]:
    out: set[int] = set()
    if value is None:
        return out
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
        for p in parts:
            if not p:
                continue
            try:
                out.add(int(p))
            except Exception:
                continue
        return out
    if isinstance(value, (list, tuple, set)):
        for v in value:
            try:
                out.add(int(v))
            except Exception:
                continue
    return out


def _to_opt_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


@dataclass(frozen=True)
class OwnerSettings:
    owner_ids: set[int]
    admin_ids: set[int]
    banned_ids: set[int]
    code_bypass_ids: set[int]
    dev_guild_id: int
    embed_echo_guild_id: Optional[int]
    embed_echo_channel_ids: set[int]
    embed_echo_user_ids: Optional[set[int]]
    embed_echo_delete_source: bool
    embed_echo_ignore_prefix_commands: bool
    verify_guild_id: int
    verify_channel_id: int
    verify_role_id: int
    verify_button_custom_id: str
    beta_announcement_channel_id: int
    beta_claim_custom_id: str


def _default_settings() -> dict[str, Any]:
    return {
        "owner_ids": [764310943781617716],
        "admin_ids": [],
        "banned_ids": [891797928396587059],
        "code_bypass_ids": [],
        "dev_guild_id": 889548793912123392,
        "embed_echo": {
            "guild_id": 889548793912123392,
            "channel_ids": [907370913002049628, 1459363727483600990, 1465864011223535774],
            "user_ids": None,
            "delete_source": True,
            "ignore_prefix_commands": True,
        },
        "verify": {
            "guild_id": 889548793912123392,
            "channel_id": 907370913002049628,
            "role_id": 907370845167566929,
            "button_custom_id": "verify:accept_rules",
        },
        "beta": {
            "announcement_channel_id": 1464033412183752808,
            "claim_custom_id": "beta_claim",
        },
    }


def load_owner_settings(path: str | None = None) -> OwnerSettings:
    """
    Load owner-editable bot settings from JSON.
    Default path: config/owner_settings.json (or OWNER_SETTINGS_PATH env).
    """
    cfg_path = Path(path or os.getenv("OWNER_SETTINGS_PATH", "config/owner_settings.json"))
    raw = _default_settings()
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                raw.update(data)
        except Exception:
            pass

    embed_cfg = raw.get("embed_echo") if isinstance(raw.get("embed_echo"), dict) else {}
    verify_cfg = raw.get("verify") if isinstance(raw.get("verify"), dict) else {}
    beta_cfg = raw.get("beta") if isinstance(raw.get("beta"), dict) else {}

    owner_ids = _to_int_set(raw.get("owner_ids"))
    if not owner_ids:
        owner_ids = {764310943781617716}

    # Optional env override for code bypass IDs remains supported.
    env_bypass = _to_int_set(os.getenv("CODE_BYPASS_IDS", ""))

    echo_user_ids_raw = embed_cfg.get("user_ids")
    echo_user_ids = _to_int_set(echo_user_ids_raw) if echo_user_ids_raw is not None else None

    return OwnerSettings(
        owner_ids=owner_ids,
        admin_ids=_to_int_set(raw.get("admin_ids")),
        banned_ids=_to_int_set(raw.get("banned_ids")),
        code_bypass_ids=_to_int_set(raw.get("code_bypass_ids")) | env_bypass,
        dev_guild_id=int(_to_opt_int(raw.get("dev_guild_id"), 889548793912123392) or 889548793912123392),
        embed_echo_guild_id=_to_opt_int(embed_cfg.get("guild_id"), 889548793912123392),
        embed_echo_channel_ids=_to_int_set(embed_cfg.get("channel_ids")),
        embed_echo_user_ids=echo_user_ids,
        embed_echo_delete_source=bool(embed_cfg.get("delete_source", True)),
        embed_echo_ignore_prefix_commands=bool(embed_cfg.get("ignore_prefix_commands", True)),
        verify_guild_id=int(_to_opt_int(verify_cfg.get("guild_id"), 889548793912123392) or 889548793912123392),
        verify_channel_id=int(_to_opt_int(verify_cfg.get("channel_id"), 907370913002049628) or 907370913002049628),
        verify_role_id=int(_to_opt_int(verify_cfg.get("role_id"), 907370845167566929) or 907370845167566929),
        verify_button_custom_id=str(verify_cfg.get("button_custom_id") or "verify:accept_rules"),
        beta_announcement_channel_id=int(
            _to_opt_int(beta_cfg.get("announcement_channel_id"), 1464033412183752808) or 1464033412183752808
        ),
        beta_claim_custom_id=str(beta_cfg.get("claim_custom_id") or "beta_claim"),
    )
