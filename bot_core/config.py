"""
Bot configuration - env vars, owner settings, constants.
"""
from __future__ import annotations

import os
import discord
from lib.owner_settings import load_owner_settings

_OWNER_SETTINGS = load_owner_settings()

# EXP Share (Gen VI+): when True, all non-fainted party mons gain full EXP
EXP_SHARE_ALWAYS_ON = str(os.getenv("EXP_SHARE_ALWAYS_ON", "0")).strip().lower() in {"1", "true", "yes", "on"}

TOKEN = (os.getenv("DISCORD_TOKEN") or "").strip()
if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in .env — add DISCORD_TOKEN=your_bot_token to .env")

# Owner / admin / verification IDs
OWNER_IDS: set[int] = set(_OWNER_SETTINGS.owner_ids)
STATIC_ADMIN_IDS: set[int] = set(_OWNER_SETTINGS.admin_ids)
BANNED_IDS: frozenset[int] = frozenset(_OWNER_SETTINGS.banned_ids)
CODE_BYPASS_IDS: frozenset[int] = frozenset(_OWNER_SETTINGS.code_bypass_ids)

DEV_GUILD_ID = int(_OWNER_SETTINGS.dev_guild_id)
DEV_GUILD = discord.Object(id=DEV_GUILD_ID)

# Embed echo
EMBED_ECHO_GUILD_ID: int | None = _OWNER_SETTINGS.embed_echo_guild_id
EMBED_ECHO_CHANNEL_IDS: set[int] = set(_OWNER_SETTINGS.embed_echo_channel_ids)
EMBED_ECHO_USER_IDS: set[int] | None = (
    set(_OWNER_SETTINGS.embed_echo_user_ids)
    if _OWNER_SETTINGS.embed_echo_user_ids is not None
    else None
)
EMBED_ECHO_DELETE_SOURCE = bool(_OWNER_SETTINGS.embed_echo_delete_source)
EMBED_ECHO_IGNORE_PREFIX_COMMANDS = bool(_OWNER_SETTINGS.embed_echo_ignore_prefix_commands)

# Verification
VERIFY_GUILD_ID = int(_OWNER_SETTINGS.verify_guild_id)
VERIFY_CHANNEL_ID = int(_OWNER_SETTINGS.verify_channel_id)
VERIFY_ROLE_ID = int(_OWNER_SETTINGS.verify_role_id)
VERIFY_BUTTON_CUSTOM_ID = str(_OWNER_SETTINGS.verify_button_custom_id)

# Beta claim
BETA_ANNOUNCEMENT_CHANNEL_ID = int(_OWNER_SETTINGS.beta_announcement_channel_id)
BETA_CLAIM_CUSTOM_ID = str(_OWNER_SETTINGS.beta_claim_custom_id)

# Access code gate
BOT_ACCESS_CODE: str = (os.getenv("BOT_ACCESS_CODE") or "").strip()
