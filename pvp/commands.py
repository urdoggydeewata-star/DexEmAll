from __future__ import annotations

import sys
import pathlib
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.errors import NotFound

# ensure project root in sys.path for local dev
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from .manager import get_manager
from .panel import AcceptView, BattleState, _turn_loop
from .formats import list_formats, get_format, get_available_generations
from .legality import validate_team
from .db_adapter import get_party_for_engine
from .engine import build_party_from_db, build_mon, Mon
from .advanced_mechanics import Substitute

class PvPCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _ephemeral(self, itx: discord.Interaction, content: str):
        # If response is not done, we can send directly
        # If response is done (deferred or already sent), use followup
        if not itx.response.is_done():
            await itx.response.send_message(content, ephemeral=True)
        else:
            await itx.followup.send(content, ephemeral=True)

    @app_commands.command(name="pvp_challenge", description="Challenge a user to a PvP battle.")
    @app_commands.describe(
        opponent="Who do you challenge?",
        format="Battle format (ou, ubers)",
        generation="Generation to use (1-9)"
    )
    async def pvp_challenge(
        self, 
        itx: discord.Interaction, 
        opponent: discord.Member, 
        format: Optional[str] = None,
        generation: Optional[int] = None
    ):
        # CRITICAL: Defer IMMEDIATELY as the VERY FIRST thing
        # Discord interactions expire in 3 seconds - don't do ANYTHING before deferring
        # Not even print statements, not even checking is_done()
        try:
            await itx.response.defer(ephemeral=False)
        except NotFound:
            # Interaction expired - can't do anything
            return
        except Exception:
            # If defer fails for any reason, return silently
            return
        
        # After deferring, we must use followup for all responses
        try:
            # Allow battling bots (AI opponents)
            is_bot_opponent = opponent.bot if hasattr(opponent, 'bot') else False
            if opponent.id == itx.user.id:
                await itx.followup.send("You can't battle yourself.", ephemeral=True)
                return

            # Get available formats
            formats = await list_formats()
            fmt_key = (format or "testing").lower()
            if fmt_key not in formats:
                fmt_key = "testing"
            
            # Validate generation
            available_gens = await get_available_generations(fmt_key)
            if generation is None:
                generation = max(available_gens)
            elif generation not in available_gens:
                await itx.followup.send(f"Generation {generation} not available for {fmt_key.upper()}. Available: {', '.join(map(str, available_gens))}", ephemeral=True)
                return

            fmt_label = formats[fmt_key]["label"]

            bm = get_manager()
            if bm.for_user(itx.user.id) or bm.for_user(opponent.id):
                await itx.followup.send("One of you is already in a battle.", ephemeral=True)
                return

            # Validate both teams before creating challenge
            # Skip validation for bot opponents (they generate teams dynamically)
            try:
                # Get format rules
                format_rules = await get_format(fmt_key, generation)
                
                # Load challenger's team
                p1_team_data = await get_party_for_engine(itx.user.id)
                
                if not p1_team_data:
                    await itx.followup.send(f"<@{itx.user.id}> has no Pokémon in their team!", ephemeral=True)
                    return
                
                # Only validate opponent's team if they're not a bot
                if not is_bot_opponent:
                    p2_team_data = await get_party_for_engine(opponent.id)
                    
                    if not p2_team_data:
                        await itx.followup.send(f"<@{opponent.id}> has no Pokémon in their team!", ephemeral=True)
                        return
                    
                    # Validate teams (skip validation for Testing format)
                    if fmt_key.lower() != "testing":
                        p1_valid, p1_errors = validate_team(p1_team_data, format_rules.rules, generation)
                        p2_valid, p2_errors = validate_team(p2_team_data, format_rules.rules, generation)
                        
                        if not p1_valid:
                            error_msg = f"<@{itx.user.id}>'s team is invalid for {fmt_label} Gen {generation}:\n" + "\n".join(f"• {err}" for err in p1_errors)
                            await itx.followup.send(error_msg, ephemeral=True)
                            return
                            
                        if not p2_valid:
                            error_msg = f"<@{opponent.id}>'s team is invalid for {fmt_label} Gen {generation}:\n" + "\n".join(f"• {err}" for err in p2_errors)
                            await itx.followup.send(error_msg, ephemeral=True)
                            return
                else:
                    # For bot opponents, only validate challenger's team
                    if fmt_key.lower() != "testing":
                        p1_valid, p1_errors = validate_team(p1_team_data, format_rules.rules, generation)
                        
                        if not p1_valid:
                            error_msg = f"<@{itx.user.id}>'s team is invalid for {fmt_label} Gen {generation}:\n" + "\n".join(f"• {err}" for err in p1_errors)
                            await itx.followup.send(error_msg, ephemeral=True)
                            return
                    
            except Exception as e:
                await itx.followup.send(f"Error validating teams: {e}", ephemeral=True)
                return

            # Create battle room
            room = bm.add(
                guild_id=itx.guild_id,
                channel_id=itx.channel_id,
                challenger_id=itx.user.id,
                opponent_id=opponent.id,
                ranked=False,
                fmt_key=fmt_key,
            )

            # Public banner with Accept/Decline buttons - DON'T add to manager yet
            view = AcceptView(
                challenger_id=itx.user.id,
                opponent_id=opponent.id,
                fmt_key=fmt_key,
                fmt_label=fmt_label,
                generation=generation,
                room_id=room.id,
                p1_is_bot=False,
                p2_is_bot=is_bot_opponent,
            )
            
            # Create embed for challenge
            embed = discord.Embed(
                title="⚔️ PvP Challenge",
                description=f"**{fmt_label}** Gen {generation} — **{'Ranked' if False else 'Casual'}**",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Challenger",
                value=f"<@{itx.user.id}>",
                inline=True
            )
            embed.add_field(
                name="Opponent", 
                value=f"<@{opponent.id}>",
                inline=True
            )
            embed.add_field(
                name="Status",
                value="⏳ Waiting for both players to accept...",
                inline=False
            )
            embed.set_footer(text="Both teams validated! Both players must Accept to start.")
            
            # Use followup since we deferred the response
            message = await itx.followup.send(embed=embed, view=view)
            # Store message reference in view so we can edit it
            view.challenge_message = message
        except Exception as e:
            try:
                await itx.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
            except:
                pass

    @app_commands.command(name="pvp_forfeit", description="Forfeit your current battle.")
    async def pvp_forfeit(self, itx: discord.Interaction):
        bm = get_manager()
        room = bm.for_user(itx.user.id)
        if not room:
            await self._ephemeral(itx, "You're not in a battle.")
            return
        bm.remove(room)
        await self._ephemeral(itx, "🏳️ Forfeited. Match ended.")

    @app_commands.command(name="dummy", description="Start a battle against a shiny Magikarp for testing.")
    @app_commands.describe(
        format="Battle format (ou, ubers)",
        generation="Generation to use (1-9)"
    )
    async def dummy(
        self,
        itx: discord.Interaction,
        format: Optional[str] = None,
        generation: Optional[int] = None
    ):
        # CRITICAL: Defer IMMEDIATELY as the VERY FIRST thing
        try:
            await itx.response.defer(ephemeral=False)
        except NotFound:
            return
        except Exception:
            return
        
        try:
            # Get available formats
            formats = await list_formats()
            fmt_key = (format or "testing").lower()
            if fmt_key not in formats:
                fmt_key = "testing"
            
            # Validate generation
            available_gens = await get_available_generations(fmt_key)
            if generation is None:
                generation = max(available_gens)
            elif generation not in available_gens:
                await itx.followup.send(f"Generation {generation} not available for {fmt_key.upper()}. Available: {', '.join(map(str, available_gens))}", ephemeral=True)
                return

            fmt_label = formats[fmt_key]["label"]

            bm = get_manager()
            if bm.for_user(itx.user.id):
                await itx.followup.send("You're already in a battle.", ephemeral=True)
                return

            # Validate challenger's team
            try:
                format_rules = await get_format(fmt_key, generation)
                p1_team_data = await get_party_for_engine(itx.user.id)
                
                if not p1_team_data:
                    await itx.followup.send(f"<@{itx.user.id}> has no Pokémon in their team!", ephemeral=True)
                    return
                
                if fmt_key.lower() != "testing":
                    p1_valid, p1_errors = validate_team(p1_team_data, format_rules.rules, generation)
                    if not p1_valid:
                        error_msg = f"<@{itx.user.id}>'s team is invalid for {fmt_label} Gen {generation}:\n" + "\n".join(f"• {err}" for err in p1_errors)
                        await itx.followup.send(error_msg, ephemeral=True)
                        return
            except Exception as e:
                await itx.followup.send(f"Error validating team: {e}", ephemeral=True)
                return

            # Create a dummy opponent ID (negative to indicate it's a dummy)
            dummy_opponent_id = -itx.user.id - 1

            # Create battle room
            room = bm.add(
                guild_id=itx.guild_id,
                channel_id=itx.channel_id,
                challenger_id=itx.user.id,
                opponent_id=dummy_opponent_id,
                ranked=False,
                fmt_key=fmt_key,
            )

            # Start battle immediately (no accept needed for dummy)
            try:
                channel = itx.channel
                
                # Load player's party
                p1_party = await build_party_from_db(itx.user.id, set_level=100, heal=True)
                if not p1_party:
                    await channel.send("Could not load your team.")
                    bm.remove(room)
                    return

                # Generate dummy opponent team with immortal substitute
                p2_party = _generate_dummy_team_with_immortal_substitute()

                await channel.send(
                    f"**Battle against Shiny Magikarp started!** <@{itx.user.id}> is testing against a shiny Magikarp.\n"
                    f"Format: **{fmt_label}** (Gen {generation})"
                )

                p1_itx = itx
                p1_name = p1_itx.user.display_name if hasattr(p1_itx.user, 'display_name') else p1_itx.user.name
                p2_name = "Shiny Magikarp"

                st = BattleState(fmt_label, generation, itx.user.id, dummy_opponent_id, p1_party, p2_party, p1_name, p2_name, p1_is_bot=False, p2_is_bot=True, is_dummy_battle=True)
                
                # Create a minimal interaction-like object for dummy opponent
                class DummyInteraction:
                    def __init__(self, user_id):
                        self.user = type('User', (), {'id': user_id, 'display_name': 'Shiny Magikarp', 'name': 'Magikarp'})()
                        self.channel = itx.channel
                        self.guild_id = itx.guild_id
                        class MockFollowup:
                            async def send(self, *args, **kwargs):
                                return None
                        self._followup = MockFollowup()
                    
                    @property
                    def followup(self):
                        return self._followup
                
                p2_itx = DummyInteraction(dummy_opponent_id)
                
                await _turn_loop(st, p1_itx, p2_itx, room_id=room.id)
            except Exception as e:
                print(f"[Dummy] Battle start error: {e}")
                import traceback
                traceback.print_exc()
                try:
                    await channel.send(f"⚠️ Battle failed to start: {str(e)}")
                except:
                    pass
                bm.remove(room)
        except Exception as e:
            try:
                await itx.followup.send(f"❌ An error occurred: {str(e)}", ephemeral=True)
            except:
                pass


def _generate_dummy_team_with_immortal_substitute() -> list[Mon]:
    """Generate a dummy opponent team with a shiny Magikarp for testing."""
    # Create a shiny Magikarp with Rattled ability and Tackle
    # This Magikarp has special behavior: always outspeeds, Tackle always brings target to 50% HP
    # and fails if user isn't at full HP or is at 50% HP
    
    magikarp = build_mon({
        "species": "Magikarp",
        "types": ("Untyped", None),  # Untyped type like MissingNo
        "base": dict(hp=20, atk=10, defn=55, spa=15, spd=20, spe=80),  # Standard Magikarp base stats
        "ivs": dict(hp=31, atk=31, defn=31, spa=31, spd=31, spe=31),
        "evs": dict(hp=0, atk=0, defn=0, spa=0, spd=0, spe=252),  # Max speed EVs
        "level": 100,
        "moves": ["Tackle"],  # Only Tackle
        "is_shiny": True,  # Shiny Magikarp
        "gender": None,
        "hp_now": 999,  # Set to 999 HP
        "ability": "Rattled",  # Rattled ability
        "item": None,
        "nature": "Jolly"  # Jolly nature for speed boost
    }, set_level=100, heal=True)
    
    # Override HP to 999
    magikarp.max_hp = 999
    magikarp.hp = 999
    
    # Set extremely high speed to ensure Magikarp always outspeeds
    # Override the calculated speed stat
    magikarp.stats["spe"] = 99999
    
    # Mark this as a dummy Magikarp for special handling
    magikarp._is_dummy_magikarp = True
    
    # Return a team with just this Magikarp
    return [magikarp]


async def setup(bot: commands.Bot):
    await bot.add_cog(PvPCog(bot))
