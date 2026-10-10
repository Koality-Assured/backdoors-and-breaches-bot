"""
Interactive Discord Views and UI Components for Backdoors & Breaches.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

import discord

from bnb.models import Card, CardType, GamePhase
from bnb.ui.embeds import (
    create_card_embed,
    create_game_status_embed,
    create_hand_embed,
    create_inject_embed,
    create_roll_embed,
    create_scenario_embed,
)

if TYPE_CHECKING:
    from bnb.deck_loader import DeckLoader
    from bnb.engine import BnbGame

logger = logging.getLogger(__name__)


class GameLobbyView(discord.ui.View):
    """Lobby controls allowing defenders to join, leave, or start the session."""

    def __init__(self, game: BnbGame, deck_loader: DeckLoader, timeout: float = 600.0) -> None:
        super().__init__(timeout=timeout)
        self.game = game
        self.deck_loader = deck_loader

    @discord.ui.button(label="Join Game", style=discord.ButtonStyle.green, emoji="🎮")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.game.phase != GamePhase.LOBBY:
            await interaction.response.send_message("This game has already started.", ephemeral=True)
            return

        added = self.game.add_player(interaction.user.id, interaction.user.display_name)
        if added:
            players_list = ", ".join(p.display_name for p in self.game.players.values())
            await interaction.response.send_message(
                f"✅ **{interaction.user.display_name}** joined the incident response exercise!\n"
                f"Defenders ({len(self.game.players)}): {players_list}",
            )
        else:
            await interaction.response.send_message("You are already in the lobby.", ephemeral=True)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.grey, emoji="🚪")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id == self.game.incident_master_id:
            await interaction.response.send_message("The Incident Master cannot leave the lobby. End the game instead.", ephemeral=True)
            return

        removed = self.game.remove_player(interaction.user.id)
        if removed:
            await interaction.response.send_message(f"**{interaction.user.display_name}** left the game.", ephemeral=True)
        else:
            await interaction.response.send_message("You are not currently in this game.", ephemeral=True)

    @discord.ui.button(label="Start Game", style=discord.ButtonStyle.primary, emoji="🚀")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.game.incident_master_id:
            await interaction.response.send_message("Only the Incident Master can start the game.", ephemeral=True)
            return

        success = self.game.start_game(self.deck_loader)
        if not success:
            await interaction.response.send_message("Failed to initialize game scenario. Please check decks.", ephemeral=True)
            return

        self.stop()
        scenario_embed = create_scenario_embed(self.game, show_secrets=False)
        turn_view = PlayerTurnView(self.game, self.deck_loader)

        curr_player = self.game.get_current_player()
        mention = f"<@{curr_player.user_id}>" if curr_player else "Defenders"

        await interaction.response.send_message(
            f"🚨 **INCIDENT UNDERWAY!** 🚨\nRound 1 has begun. It is {mention}'s turn!\n"
            f"Defenders have received their private hands. Use the controls below to play procedures.",
            embed=scenario_embed,
            view=turn_view,
        )


class PlayerTurnView(discord.ui.View):
    """In-game control view for active turns."""

    def __init__(self, game: BnbGame, deck_loader: DeckLoader, timeout: float = 1200.0) -> None:
        super().__init__(timeout=timeout)
        self.game = game
        self.deck_loader = deck_loader

    @discord.ui.button(label="Play Procedure", style=discord.ButtonStyle.green, emoji="🛠️")
    async def play_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        curr_player = self.game.get_current_player()
        if not curr_player or curr_player.user_id != interaction.user.id:
            await interaction.response.send_message("It is not currently your turn.", ephemeral=True)
            return

        # Present the procedure card selection menu
        select_view = ProcedureSelectView(self.game, self.deck_loader, curr_player)
        await interaction.response.send_message(
            "Select a Procedure card from your hand (or common procedures) and choose your target vector:",
            view=select_view,
            ephemeral=True,
        )

    @discord.ui.button(label="View Hand", style=discord.ButtonStyle.secondary, emoji="🃏")
    async def hand_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self.game.players.get(interaction.user.id)
        if not player:
            await interaction.response.send_message("You are not part of this game.", ephemeral=True)
            return
        hand_embed = create_hand_embed(player)
        await interaction.response.send_message(embed=hand_embed, ephemeral=True)

    @discord.ui.button(label="Game Status", style=discord.ButtonStyle.grey, emoji="📋")
    async def status_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        status_embed = create_game_status_embed(self.game)
        await interaction.response.send_message(embed=status_embed, ephemeral=True)

    @discord.ui.button(label="Pass Turn", style=discord.ButtonStyle.red, emoji="⏭️")
    async def pass_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        curr_player = self.game.get_current_player()
        if not curr_player or curr_player.user_id != interaction.user.id:
            await interaction.response.send_message("It is not currently your turn.", ephemeral=True)
            return

        passed = self.game.pass_turn(interaction.user.id)
        if passed:
            next_player = self.game.get_current_player()
            next_mention = f"<@{next_player.user_id}>" if next_player else "Defenders"
            await interaction.response.send_message(
                f"⏭️ **{interaction.user.display_name}** passed their turn. It is now {next_mention}'s turn!"
            )


class ProcedureSelectView(discord.ui.View):
    """Ephemeral selection view for choosing card and target vector."""

    def __init__(self, game: BnbGame, deck_loader: DeckLoader, player, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.game = game
        self.deck_loader = deck_loader
        self.player = player
        self.selected_card_name: Optional[str] = None
        self.selected_target: Optional[CardType] = None

        # Build card options: player hand cards (+3) followed by common procedures
        options: List[discord.SelectOption] = []
        for card in self.player.hand:
            is_cd = self.game.is_card_on_cooldown(card.name)
            options.append(
                discord.SelectOption(
                    label=card.name[:95],
                    value=card.name,
                    description=f"In Hand (+3 bonus){' [COOLDOWN]' if is_cd else ''}",
                    emoji="🃏",
                )
            )

        # Also offer common procedures from the deck if hand has few cards
        common_procs = [
            c for c in self.deck_loader.get_all_cards(self.game.deck_id)
            if c.type == CardType.PROCEDURE and c.name not in [h.name for h in self.player.hand]
        ][:15]

        for card in common_procs:
            if len(options) >= 25:
                break
            is_cd = self.game.is_card_on_cooldown(card.name)
            options.append(
                discord.SelectOption(
                    label=card.name[:95],
                    value=card.name,
                    description=f"Deck pool (+0 bonus){' [COOLDOWN]' if is_cd else ''}",
                    emoji="🛠️",
                )
            )

        if options:
            self.card_select = discord.ui.Select(
                placeholder="Choose a Procedure Card to play...",
                options=options[:25],
                row=0,
            )
            self.card_select.callback = self._on_card_select
            self.add_item(self.card_select)

        # Target vector selection
        vector_options = [
            discord.SelectOption(label="Any / Incident Master Discretion", value="any", emoji="❓"),
            discord.SelectOption(label="Initial Compromise", value=CardType.INITIAL.value, emoji="🎯"),
            discord.SelectOption(label="Pivot & Escalate", value=CardType.PIVOT.value, emoji="🔀"),
            discord.SelectOption(label="Persistence", value=CardType.PERSIST.value, emoji="⚓"),
            discord.SelectOption(label="C2 & Exfiltration", value=CardType.C2.value, emoji="📡"),
        ]
        self.target_select = discord.ui.Select(
            placeholder="Target Attack Vector to investigate...",
            options=vector_options,
            row=1,
        )
        self.target_select.callback = self._on_target_select
        self.add_item(self.target_select)

    async def _on_card_select(self, interaction: discord.Interaction) -> None:
        self.selected_card_name = self.card_select.values[0]
        await interaction.response.defer()

    async def _on_target_select(self, interaction: discord.Interaction) -> None:
        val = self.target_select.values[0]
        self.selected_target = None if val == "any" else CardType(val)
        await interaction.response.defer()

    @discord.ui.button(label="Roll D20 & Execute", style=discord.ButtonStyle.primary, emoji="🎲", row=2)
    async def roll_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.selected_card_name:
            await interaction.response.send_message("Please select a procedure card first.", ephemeral=True)
            return

        try:
            result = self.game.play_procedure(
                user_id=interaction.user.id,
                card_name=self.selected_card_name,
                target_category=self.selected_target,
            )
        except Exception as exc:
            await interaction.response.send_message(f"Error: {exc}", ephemeral=True)
            return

        self.stop()
        roll_embed = create_roll_embed(result)

        # Send card artwork if available
        files: List[discord.File] = []
        if result.card.image_path:
            try:
                files.append(discord.File(result.card.image_path, filename="card_art.png"))
                roll_embed.set_thumbnail(url="attachment://card_art.png")
            except Exception:
                pass

        await interaction.response.send_message(
            f"🎲 **{interaction.user.display_name}** played **{result.card.name}**!",
            embed=roll_embed,
            files=files,
        )

        # If game concluded, announce victory or defeat
        if self.game.phase == GamePhase.VICTORY:
            victory_embed = create_scenario_embed(self.game, show_secrets=True)
            await interaction.channel.send(
                "🏆 **DEFENDERS WIN!** 🏆\nAll 4 attack vectors have been uncovered and neutralized! Great work team!",
                embed=victory_embed,
            )
        elif self.game.phase == GamePhase.DEFEAT:
            defeat_embed = create_scenario_embed(self.game, show_secrets=True)
            await interaction.channel.send(
                "💀 **INCIDENT RESPONSE FAILED (Turn Limit Reached)** 💀\nThe adversaries successfully completed their attack.",
                embed=defeat_embed,
            )


class IncidentMasterControlView(discord.ui.View):
    """Private control panel for the Incident Master."""

    def __init__(self, game: BnbGame, deck_loader: DeckLoader, timeout: float = 1800.0) -> None:
        super().__init__(timeout=timeout)
        self.game = game
        self.deck_loader = deck_loader

    @discord.ui.button(label="View Secret Attack Vectors", style=discord.ButtonStyle.primary, emoji="👁️")
    async def view_vectors(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.game.incident_master_id:
            await interaction.response.send_message("Only the Incident Master can view secret vectors.", ephemeral=True)
            return
        secret_embed = create_scenario_embed(self.game, show_secrets=True)
        await interaction.response.send_message(embed=secret_embed, ephemeral=True)

    @discord.ui.button(label="Draw Inject", style=discord.ButtonStyle.secondary, emoji="💉")
    async def draw_inject_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.game.incident_master_id:
            await interaction.response.send_message("Only the Incident Master can trigger manual injects.", ephemeral=True)
            return

        inject_card = self.game.draw_inject()
        inject_embed = create_inject_embed(inject_card, reason="Incident Master manual injection")

        files: List[discord.File] = []
        if inject_card.image_path:
            try:
                files.append(discord.File(inject_card.image_path, filename="inject.png"))
                inject_embed.set_image(url="attachment://inject.png")
            except Exception:
                pass

        await interaction.channel.send(
            "💉 **INCIDENT MASTER TRIGGERED AN INJECT!**",
            embed=inject_embed,
            files=files,
        )
        await interaction.response.send_message("Inject broadcast to channel.", ephemeral=True)

    @discord.ui.button(label="End Game", style=discord.ButtonStyle.danger, emoji="🛑")
    async def end_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.game.incident_master_id:
            await interaction.response.send_message("Only the Incident Master can end the game.", ephemeral=True)
            return

        self.game.end_game("Concluded by Incident Master.")
        self.stop()
        final_embed = create_scenario_embed(self.game, show_secrets=True)
        await interaction.channel.send(
            f"🛑 The incident response exercise was ended by {interaction.user.mention}.",
            embed=final_embed,
        )
        await interaction.response.send_message("Game ended.", ephemeral=True)


class CardPagingView(discord.ui.View):
    """Paging navigator for browsing card lists and search results."""

    def __init__(self, cards: List[Card], timeout: float = 300.0) -> None:
        super().__init__(timeout=timeout)
        self.cards = cards
        self.current_page = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.current_page == 0
        self.next_btn.disabled = self.current_page >= len(self.cards) - 1
        self.page_indicator.label = f"Card {self.current_page + 1} of {len(self.cards)}"

    def get_current_embed_and_file(self) -> tuple[discord.Embed, Optional[discord.File]]:
        card = self.cards[self.current_page]
        file_obj = None
        attach_name = None
        if card.image_path:
            try:
                attach_name = f"card_{card.id}.png"
                file_obj = discord.File(card.image_path, filename=attach_name)
            except Exception:
                pass

        embed = create_card_embed(card, file_attachment_name=attach_name)
        return embed, file_obj

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.grey)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            embed, file_obj = self.get_current_embed_and_file()
            kwargs = {"embed": embed, "view": self}
            if file_obj:
                kwargs["attachments"] = [file_obj]
            await interaction.response.edit_message(**kwargs)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Page 1 of 1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.grey)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_page < len(self.cards) - 1:
            self.current_page += 1
            self._update_buttons()
            embed, file_obj = self.get_current_embed_and_file()
            kwargs = {"embed": embed, "view": self}
            if file_obj:
                kwargs["attachments"] = [file_obj]
            await interaction.response.edit_message(**kwargs)
        else:
            await interaction.response.defer()


class FacilitatorView(discord.ui.View):
    """Utility buttons for tabletop facilitator / voice channel sessions."""

    def __init__(self, deck_loader: DeckLoader, deck_id: Optional[str] = None, timeout: float = 600.0) -> None:
        super().__init__(timeout=timeout)
        self.deck_loader = deck_loader
        self.deck_id = deck_id

    @discord.ui.button(label="Roll D20", style=discord.ButtonStyle.primary, emoji="🎲")
    async def roll_d20(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        import random
        val = random.randint(1, 20)
        color = 0xF59E0B if val == 20 else (0x991B1B if val == 1 else (0x10B981 if val >= 11 else 0xEF4444))
        embed = discord.Embed(
            title=f"🎲 Tabletop D20 Roll: **{val}**",
            description=f"{interaction.user.mention} rolled a **{val}** on a 20-sided die.",
            color=color,
        )
        embed.set_footer(text=f"Target: 11+ {'(Success)' if val >= 11 else '(Failure)'}")
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Draw Inject", style=discord.ButtonStyle.secondary, emoji="💉")
    async def draw_inject(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        inject_card = self.deck_loader.get_random_card(CardType.INJECT, self.deck_id)
        if not inject_card:
            await interaction.response.send_message("No Inject cards available.", ephemeral=True)
            return

        embed = create_inject_embed(inject_card, reason="Drawn by Facilitator")
        files: List[discord.File] = []
        if inject_card.image_path:
            try:
                files.append(discord.File(inject_card.image_path, filename="inject.png"))
                embed.set_image(url="attachment://inject.png")
            except Exception:
                pass
        await interaction.response.send_message(embed=embed, files=files)
