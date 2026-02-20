from __future__ import annotations

from typing import List, Dict, Any
import discord
from discord import app_commands
from discord.ext import commands

from .formats import get_format, list_formats, get_available_generations


def _pretty_list(values: List[str]) -> str:
    return ", ".join(values) if values else "None"


def _clauses_list(rules: Dict[str, Any]) -> List[str]:
    # Show only truthy clauses; keep insertion order as in dict
    clauses = rules.get("clauses") or {}
    out = []
    for k, v in clauses.items():
        if v:
            # friendlier names
            name = k.replace("_", " ").title()
            out.append(name)
    return out


class RulesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- Autocompletes ----------
    async def _fmt_autocomplete(self, itx: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for format selection"""
        try:
            formats = await list_formats()
            choices = []
            for key, info in formats.items():
                label = info.get("label", key.upper())
                if not current or key.startswith(current.lower()) or label.lower().startswith(current.lower()):
                    choices.append(app_commands.Choice(name=label, value=key))
            return choices[:25]  # Discord limit
        except Exception:
            return [
                app_commands.Choice(name="OverUsed", value="ou"),
                app_commands.Choice(name="Ubers", value="ubers")
            ]

    async def _gen_autocomplete(self, itx: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete for generation selection"""
        try:
            # Get the format from the current interaction namespace
            fmt_key = getattr(itx.namespace, "fmt", "ou") or "ou"
            gens = await get_available_generations(fmt_key)
            choices = []
            for g in gens:
                if not current or str(g).startswith(current):
                    choices.append(app_commands.Choice(name=f"Gen {g}", value=str(g)))
            return choices
        except Exception:
            # Fallback to all gens
            return [app_commands.Choice(name=f"Gen {g}", value=str(g)) for g in range(1, 10)]

    # ---------- Command ----------
    @app_commands.command(name="pvprules", description="Show PvP rules for a format and generation.")
    @app_commands.describe(fmt="Format key (e.g., ou)", gen="Generation number")
    @app_commands.autocomplete(fmt=_fmt_autocomplete, gen=_gen_autocomplete)
    async def pvprules(self, itx: discord.Interaction, fmt: str, gen: str):
        fmt_key = (fmt or "ou").lower()

        # Get available formats
        formats = await list_formats()
        
        # Validate format
        if fmt_key not in formats:
            await itx.response.send_message(f"Unknown format `{fmt}`. Try one of: {', '.join(formats.keys())}", ephemeral=True)
            return

        # Validate/parse gen
        try:
            g_req = int(gen)
        except (TypeError, ValueError):
            gens = await get_available_generations(fmt_key)
            await itx.response.send_message(f"Invalid gen `{gen}`. Available: {', '.join(map(str, gens))}", ephemeral=True)
            return

        # Check if gen is available for this format
        available_gens = await get_available_generations(fmt_key)
        if g_req not in available_gens:
            await itx.response.send_message(f"`{formats[fmt_key]['label']}` doesn't have Gen {g_req}. Available: {', '.join(map(str, available_gens))}", ephemeral=True)
            return

        fr = await get_format(fmt_key, g_req)  # -> FormatRules(label, gen, rules dict)
        r = fr.rules

        # Build embed
        em = discord.Embed(
            title=f"{fr.label} — Gen {fr.gen} Rules",
            color=discord.Color.blurple()
        )

        # Clauses
        clauses = _clauses_list(r)
        em.add_field(name="Clauses", value=_pretty_list(clauses), inline=False)

        # Bans
        em.add_field(name="Species Bans", value=_pretty_list(r.get("species_bans", [])), inline=False)
        em.add_field(name="Ability Bans", value=_pretty_list(r.get("ability_bans", [])), inline=False)
        em.add_field(name="Move Bans", value=_pretty_list(r.get("move_bans", [])), inline=False)
        em.add_field(name="Item Bans", value=_pretty_list(r.get("item_bans", [])), inline=False)

        # Combo bans (if any)
        team_combo = r.get("team_combo_bans", [])
        mon_combo = r.get("mon_combo_bans", [])
        if team_combo:
            em.add_field(name="Team Combo Bans", value=_pretty_list(team_combo), inline=False)
        if mon_combo:
            em.add_field(name="Mon Combo Bans", value=_pretty_list(mon_combo), inline=False)

        # Generation cap (prevents higher-gen mons)
        if "max_mon_gen" in r:
            em.add_field(name="Max Pokémon Generation", value=str(r["max_mon_gen"]), inline=True)

        await itx.response.send_message(embed=em, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RulesCog(bot))