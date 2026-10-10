"""
Interactive game management cog for Backdoors & Breaches.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from bnb.config import Settings
from bnb.deck_loader import DeckLoader
from bnb.engine import GameManager
from bnb.models import CardType, GamePhase
from bnb.ui.embeds import (
    create_game_status_embed,
    create_hand_embed,
    create_roll_embed,
    create_scenario_embed,
)
from bnb.ui.views import (
    GameLobbyView,
    IncidentMasterControlView,
    PlayerTurnView,
)

logger = logging.getLogger(__name__)


class GameCog(commands.Cog, name="Game"):
    """Interactive Incident Response Game Commands."""

    def __init__(self, bot: commands.Bot, deck_loader: DeckLoader, game_manager: GameManager, settings: Settings) -> None:
        self.bot = bot
        self.deck_loader = deck_loader
        self.game_manager = game_manager
        self.settings = settings

    async def deck_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete available deck names."""
        decks = self.deck_loader.list_decks()
        choices = []
        for d in decks:
            if current.lower() in d.title.lower() or current.lower() in d.id.lower():
                choices.append(app_commands.Choice(name=f"{d.title} ({len(d.cards)} cards)", value=d.id))
        return choices[:25]

    async def procedure_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete procedure cards in player hand or deck."""
        game = self.game_manager.get_game(interaction.channel_id)
        choices = []
        if game and interaction.user.id in game.players:
            player = game.players[interaction.user.id]
            for c in player.hand:
                if current.lower() in c.name.lower():
                    choices.append(app_commands.Choice(name=f"🃏 Hand: {c.name[:80]}", value=c.name))

        # Also search general procedures
        procs = self.deck_loader.search_cards(current, card_type=CardType.PROCEDURE, limit=15)
        for c in procs:
            if c.name not in [ch.value for ch in choices]:
                choices.append(app_commands.Choice(name=f"🛠️ {c.name[:85]}", value=c.name))
        return choices[:25]

    @commands.hybrid_group(name="game", description="Backdoors & Breaches interactive game commands.")
    async def game_group(self, ctx: commands.Context) -> None:
        """Parent command group for interactive games."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Use `/game setup`, `/game join`, `/game start`, or `/game status`.")

    @game_group.command(name="setup", description="Set up a new incident response game in this channel.")
    @app_commands.describe(deck="Select which card expansion deck to play with")
    @app_commands.autocomplete(deck=deck_autocomplete)
    async def setup_game(self, ctx: commands.Context, deck: Optional[str] = None) -> None:
        """Initialize a new game lobby in the channel."""
        if not self.settings.is_channel_allowed(ctx.channel.id):
            await ctx.reply("❌ Games are not permitted in this channel per server configuration.", ephemeral=True)
            return

        existing = self.game_manager.get_game(ctx.channel.id)
        if existing and existing.phase != GamePhase.ENDED:
            await ctx.reply(
                f"A game is already active in this channel (Phase: `{existing.phase.value}`). "
                "Use `/game status` to view it or `/game end` to terminate it.",
                ephemeral=True,
            )
            return

        chosen_deck = deck or self.settings.default_deck
        deck_obj = self.deck_loader.get_deck(chosen_deck)
        if not deck_obj:
            available = ", ".join(d.id for d in self.deck_loader.list_decks()[:6])
            await ctx.reply(
                f"❌ Unknown deck `{chosen_deck}`. Available decks include: {available}",
                ephemeral=True,
            )
            return

        game = self.game_manager.create_game(
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id if ctx.guild else 0,
            incident_master_id=ctx.author.id,
            incident_master_name=ctx.author.display_name,
            deck_id=deck_obj.id,
            max_turns=self.settings.max_turns,
            inject_failure_threshold=self.settings.inject_failure_threshold,
        )

        lobby_view = GameLobbyView(game, self.deck_loader)
        embed = discord.Embed(
            title="🛡️ Backdoors & Breaches — Incident Response Lobby",
            description=(
                f"**Incident Master:** {ctx.author.mention}\n"
                f"**Deck Selected:** {deck_obj.title} (`{deck_obj.id}`)\n"
                f"**Max Rounds:** {self.settings.max_turns} rounds\n\n"
                "Click **Join Game** below to register as a defender. Once everyone is ready, "
                "the Incident Master can click **Start Game**!"
            ),
            color=0x2563EB,
        )
        embed.set_footer(text="Backdoors & Breaches • Black Hills Information Security")
        await ctx.reply(embed=embed, view=lobby_view)

    @game_group.command(name="join", description="Join the incident response game lobby in this channel.")
    async def join_game(self, ctx: commands.Context) -> None:
        """Join the active lobby."""
        game = self.game_manager.get_game(ctx.channel.id)
        if not game:
            await ctx.reply("No game is currently set up in this channel. Run `/game setup` to create one.", ephemeral=True)
            return

        if game.phase != GamePhase.LOBBY:
            await ctx.reply("This game is already underway. Cannot join in-progress exercises.", ephemeral=True)
            return

        added = game.add_player(ctx.author.id, ctx.author.display_name)
        if added:
            await ctx.reply(f"✅ {ctx.author.mention} joined the incident response exercise! ({len(game.players)} total)")
        else:
            await ctx.reply("You are already registered in this game.", ephemeral=True)

    @game_group.command(name="start", description="Incident Master starts the exercise.")
    async def start_game(self, ctx: commands.Context) -> None:
        """Start the incident exercise."""
        game = self.game_manager.get_game(ctx.channel.id)
        if not game:
            await ctx.reply("No game to start. Run `/game setup` first.", ephemeral=True)
            return

        if ctx.author.id != game.incident_master_id:
            await ctx.reply("Only the Incident Master can start the game.", ephemeral=True)
            return

        started = game.start_game(self.deck_loader)
        if not started:
            await ctx.reply("Failed to start exercise. Please ensure decks are loaded.", ephemeral=True)
            return

        scenario_embed = create_scenario_embed(game, show_secrets=False)
        turn_view = PlayerTurnView(game, self.deck_loader)
        curr_player = game.get_current_player()
        mention = f"<@{curr_player.user_id}>" if curr_player else "Defenders"

        await ctx.reply(
            f"🚨 **INCIDENT UNDERWAY!** 🚨\nRound 1 has begun. It is {mention}'s turn!\n"
            f"Defenders have received their private hands. Use `/game hand` or the controls below.",
            embed=scenario_embed,
            view=turn_view,
        )

    @game_group.command(name="status", description="Check current game progress and round status.")
    async def game_status(self, ctx: commands.Context) -> None:
        """Display game status embed."""
        game = self.game_manager.get_game(ctx.channel.id)
        if not game:
            await ctx.reply("No active game in this channel.", ephemeral=True)
            return

        embed = create_game_status_embed(game)
        scenario = create_scenario_embed(game, show_secrets=False)
        await ctx.reply(embeds=[embed, scenario])

    @game_group.command(name="hand", description="View your private hand of Procedure cards.")
    async def game_hand(self, ctx: commands.Context) -> None:
        """Display private player hand."""
        game = self.game_manager.get_game(ctx.channel.id)
        if not game:
            await ctx.reply("No active game in this channel.", ephemeral=True)
            return

        player = game.players.get(ctx.author.id)
        if not player:
            await ctx.reply("You are not registered in this game.", ephemeral=True)
            return

        embed = create_hand_embed(player)
        await ctx.reply(embed=embed, ephemeral=True)

    @game_group.command(name="im-panel", description="Incident Master private control panel.")
    async def im_panel(self, ctx: commands.Context) -> None:
        """Display Incident Master controls."""
        game = self.game_manager.get_game(ctx.channel.id)
        if not game:
            await ctx.reply("No active game in this channel.", ephemeral=True)
            return

        if ctx.author.id != game.incident_master_id:
            await ctx.reply("Only the Incident Master has access to this panel.", ephemeral=True)
            return

        view = IncidentMasterControlView(game, self.deck_loader)
        secret_embed = create_scenario_embed(game, show_secrets=True)
        await ctx.reply(
            "🛡️ **Incident Master Control Center**\nUse these buttons to view secret threat vectors or trigger injects:",
            embed=secret_embed,
            view=view,
            ephemeral=True,
        )

    @game_group.command(name="play", description="Execute a procedure and roll d20 on your turn.")
    @app_commands.describe(
        card_name="Name of the procedure card to play",
        target="Target attack vector to investigate (optional)",
    )
    @app_commands.autocomplete(card_name=procedure_autocomplete)
    @app_commands.choices(target=[
        app_commands.Choice(name="🎯 Initial Compromise", value="initial"),
        app_commands.Choice(name="🔀 Pivot & Escalate", value="pivot"),
        app_commands.Choice(name="⚓ Persistence", value="persist"),
        app_commands.Choice(name="📡 C2 & Exfiltration", value="c2"),
    ])
    async def play_card(
        self,
        ctx: commands.Context,
        card_name: str,
        target: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        """Play a procedure card from command line."""
        game = self.game_manager.get_game(ctx.channel.id)
        if not game or game.phase != GamePhase.IN_PROGRESS:
            await ctx.reply("No game is currently in progress.", ephemeral=True)
            return

        curr_player = game.get_current_player()
        if not curr_player or curr_player.user_id != ctx.author.id:
            await ctx.reply(f"It is not your turn. Current turn: <@{curr_player.user_id}>", ephemeral=True)
            return

        target_cat = CardType.from_str(target.value) if target else None

        try:
            result = game.play_procedure(
                user_id=ctx.author.id,
                card_name=card_name,
                target_category=target_cat,
            )
        except Exception as exc:
            await ctx.reply(f"❌ {exc}", ephemeral=True)
            return

        roll_embed = create_roll_embed(result)
        files = []
        if result.card.image_path:
            try:
                files.append(discord.File(result.card.image_path, filename="card.png"))
                roll_embed.set_thumbnail(url="attachment://card.png")
            except Exception:
                pass

        await ctx.reply(
            f"🎲 {ctx.author.mention} played **{result.card.name}**!",
            embed=roll_embed,
            files=files,
        )

        # Announce victory or defeat
        if game.phase == GamePhase.VICTORY:
            victory_embed = create_scenario_embed(game, show_secrets=True)
            await ctx.send("🏆 **DEFENDERS WIN!** All attack vectors discovered and neutralized!", embed=victory_embed)
        elif game.phase == GamePhase.DEFEAT:
            defeat_embed = create_scenario_embed(game, show_secrets=True)
            await ctx.send("💀 **DEFENDERS DEFEATED (Turn limit reached).**", embed=defeat_embed)

    @game_group.command(name="pass", description="Pass your turn without playing a card.")
    async def pass_turn(self, ctx: commands.Context) -> None:
        """Pass turn."""
        game = self.game_manager.get_game(ctx.channel.id)
        if not game or game.phase != GamePhase.IN_PROGRESS:
            await ctx.reply("No game in progress.", ephemeral=True)
            return

        passed = game.pass_turn(ctx.author.id)
        if passed:
            next_player = game.get_current_player()
            await ctx.reply(f"⏭️ {ctx.author.mention} passed. Next turn: <@{next_player.user_id}>")
        else:
            await ctx.reply("It is not your turn to pass.", ephemeral=True)

    @game_group.command(name="end", description="End the current incident response game.")
    async def end_game(self, ctx: commands.Context) -> None:
        """Conclude active game."""
        game = self.game_manager.get_game(ctx.channel.id)
        if not game:
            await ctx.reply("No active game to end.", ephemeral=True)
            return

        if ctx.author.id != game.incident_master_id and not ctx.author.guild_permissions.administrator:
            await ctx.reply("Only the Incident Master or an Administrator can end the game.", ephemeral=True)
            return

        game.end_game(f"Concluded by {ctx.author.display_name}")
        self.game_manager.delete_game(ctx.channel.id)
        embed = create_scenario_embed(game, show_secrets=True)
        await ctx.reply(f"🛑 Incident response exercise ended by {ctx.author.mention}.", embed=embed)
