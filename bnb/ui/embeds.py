"""
Discord Embed generators for cards, scenarios, rolls, hands, and game status.
"""

from __future__ import annotations

from typing import List, Optional

import discord

from bnb.engine import BnbGame
from bnb.models import Card, CardType, GamePhase, Player, PlayResult

FOOTER_TEXT = "Backdoors & Breaches • Black Hills Information Security"


def create_card_embed(
    card: Card,
    file_attachment_name: Optional[str] = None,
) -> discord.Embed:
    """Generate a rich embed displaying a card's details and artwork."""
    embed = discord.Embed(
        title=f"{card.type.emoji} {card.name}",
        description=card.clean_details or "*No additional description provided.*",
        color=card.type.embed_color,
    )
    embed.add_field(name="Card Type", value=card.type.display_name, inline=True)
    embed.add_field(name="Expansion / Deck", value=card.deck_title, inline=True)
    embed.add_field(name="Card ID", value=f"`#{card.id}`", inline=True)

    if file_attachment_name:
        embed.set_image(url=f"attachment://{file_attachment_name}")
    elif card.image_path and card.image_path.startswith("http"):
        embed.set_image(url=card.image_path)

    embed.set_footer(text=FOOTER_TEXT)
    return embed


def create_scenario_embed(
    game: BnbGame,
    show_secrets: bool = False,
) -> discord.Embed:
    """Display the 4 attack vectors of an active incident scenario."""
    color = 0x10B981 if game.phase == GamePhase.VICTORY else 0x3B82F6
    status_text = "Incident Mitigated! (All Vectors Uncovered)" if game.phase == GamePhase.VICTORY else "Active Incident Investigation"

    embed = discord.Embed(
        title=f"🛡️ Backdoors & Breaches Scenario — {status_text}",
        description=f"Deck: **{game.deck_id}** • Round: **{game.turn}/{game.max_turns}** • Incident Master: **{game.incident_master_name}**",
        color=color,
    )

    for vtype in (CardType.INITIAL, CardType.PIVOT, CardType.PERSIST, CardType.C2):
        slot = game.threat_slots.get(vtype)
        if not slot:
            continue

        if slot.discovered or show_secrets:
            prefix = "✅ " if slot.discovered else "👁️ [SECRET] "
            discover_info = f"\n*Discovered in round {slot.discovered_turn} by {slot.discovered_by}*" if slot.discovered else ""
            desc = slot.card.clean_details[:250] + ("..." if len(slot.card.clean_details) > 250 else "")
            embed.add_field(
                name=f"{prefix}{vtype.emoji} {vtype.display_name}: {slot.card.name}",
                value=f"{desc}{discover_info}",
                inline=False,
            )
        else:
            embed.add_field(
                name=f"🔒 {vtype.emoji} {vtype.display_name}",
                value="*Undiscovered attack vector. Roll procedure cards to uncover.*",
                inline=False,
            )

    embed.set_footer(text=FOOTER_TEXT)
    return embed


def create_game_status_embed(game: BnbGame) -> discord.Embed:
    """Display overall game progress, turn order, cooldowns, and active injects."""
    curr_player = game.get_current_player()
    curr_player_name = curr_player.display_name if curr_player else "None"

    discovered_count = sum(1 for s in game.threat_slots.values() if s.discovered)
    total_vectors = len(game.threat_slots)

    embed = discord.Embed(
        title="📋 Incident Response Exercise Status",
        color=0x3B82F6,
    )
    embed.add_field(name="Phase", value=f"`{game.phase.value.upper()}`", inline=True)
    embed.add_field(name="Round / Max", value=f"`{game.turn} / {game.max_turns}`", inline=True)
    embed.add_field(name="Current Turn", value=f"👉 **{curr_player_name}**", inline=True)
    embed.add_field(name="Vectors Uncovered", value=f"**{discovered_count} / {total_vectors}**", inline=True)
    embed.add_field(
        name="Failed Roll Streak",
        value=f"**{game.failed_roll_streak} / {game.inject_failure_threshold}** (triggers Inject)",
        inline=True,
    )
    embed.add_field(name="Defenders Count", value=f"**{len(game.players)}**", inline=True)

    # Cooldowns list
    if game.cooldowns:
        cd_lines = [
            f"• `{name.title()}` (until round {turn_exp + 1})"
            for name, turn_exp in game.cooldowns.items()
            if turn_exp >= game.turn
        ]
        if cd_lines:
            embed.add_field(name="⏳ Active Cooldowns", value="\n".join(cd_lines), inline=False)

    # Active injects list
    if game.active_injects:
        inj_lines = [f"• 💉 **{inj.name}**" for inj in game.active_injects[-5:]]
        embed.add_field(name="⚠️ Recent Injects in Play", value="\n".join(inj_lines), inline=False)

    embed.set_footer(text=FOOTER_TEXT)
    return embed


def create_roll_embed(result: PlayResult) -> discord.Embed:
    """Display the detailed visual breakdown of a procedure roll."""
    if result.is_nat_20:
        color = 0xF59E0B  # Gold
        status_title = "🌟 CRITICAL SUCCESS! (Natural 20)"
    elif result.is_nat_1:
        color = 0x991B1B  # Deep Red
        status_title = "🚨 CRITICAL FAILURE! (Natural 1)"
    elif result.success:
        color = 0x10B981  # Green
        status_title = "✅ PROCEDURE SUCCEEDED! (Target >= 11)"
    else:
        color = 0xEF4444  # Red
        status_title = "❌ PROCEDURE FAILED! (Target < 11)"

    embed = discord.Embed(
        title=f"🎲 {status_title}",
        description=result.message,
        color=color,
    )

    roll_breakdown = (
        f"**d20 Roll:** `{result.natural_roll}`\n"
        f"**Hand Bonus:** `+{result.hand_bonus}` (in hand)\n"
        f"**Other Modifiers:** `+{result.extra_modifiers}`\n"
        f"━━━━━━━━━━━━━━━\n"
        f"**Total Roll:** `{result.total_roll}` vs **DC 11**"
    )
    embed.add_field(name="Roll Calculation", value=roll_breakdown, inline=True)
    embed.add_field(name="Card Played", value=f"🛠️ **{result.card.name}**", inline=True)

    if result.discovered_card:
        embed.add_field(
            name="Uncovered Vector!",
            value=f"**{result.discovered_card.type.display_name}:** {result.discovered_card.name}",
            inline=False,
        )

    if result.inject_drawn:
        embed.add_field(
            name="⚠️ Inject Triggered!",
            value=f"💉 **{result.inject_drawn.name}**\n{result.inject_drawn.clean_details}",
            inline=False,
        )

    embed.set_footer(text=FOOTER_TEXT)
    return embed


def create_hand_embed(player: Player) -> discord.Embed:
    """Display a player's secret hand of procedure cards."""
    embed = discord.Embed(
        title=f"🃏 Hand for {player.display_name}",
        description=(
            "Playing a card from your hand grants a **+3 modifier** to your d20 roll!\n"
            "Select one on your turn to execute the procedure."
        ),
        color=0x2563EB,
    )

    if not player.hand:
        embed.add_field(name="Empty Hand", value="*You do not have any cards in your hand.*")
    else:
        for i, card in enumerate(player.hand, 1):
            desc = card.clean_details[:150] + ("..." if len(card.clean_details) > 150 else "")
            embed.add_field(
                name=f"{i}. 🛠️ {card.name}",
                value=f"{desc}\n*Deck: {card.deck_title}*",
                inline=False,
            )

    embed.set_footer(text=FOOTER_TEXT)
    return embed


def create_inject_embed(card: Card, reason: str = "") -> discord.Embed:
    """Display an alert embed for an Inject card."""
    embed = discord.Embed(
        title=f"💉 INJECT TRIGGERED: {card.name}",
        description=card.clean_details or "*A complication has occurred in the incident!*",
        color=0xDC2626,
    )
    if reason:
        embed.add_field(name="Trigger Reason", value=reason, inline=True)
    embed.add_field(name="Expansion", value=card.deck_title, inline=True)
    embed.set_footer(text=FOOTER_TEXT)
    return embed


def create_deck_list_embed(decks: List) -> discord.Embed:
    """Display a catalog of loaded decks and card counts."""
    embed = discord.Embed(
        title="📚 Available Backdoors & Breaches Decks",
        description="Choose any deck when setting up a game with `/bnb game setup deck:<name>`.",
        color=0x3B82F6,
    )

    for deck in decks:
        total = len(deck.cards)
        counts = {}
        for c in deck.cards:
            counts[c.type.value] = counts.get(c.type.value, 0) + 1
        summary = ", ".join(f"{t}: {cnt}" for t, cnt in sorted(counts.items()))
        date_str = f" • *Rev: {deck.revdate}*" if deck.revdate else ""
        embed.add_field(
            name=f"🗂️ {deck.title} (`{deck.id}`)",
            value=f"**{total} Cards** ({summary}){date_str}",
            inline=False,
        )

    embed.set_footer(text=FOOTER_TEXT)
    return embed


def create_help_embed(prefix: str = "/") -> discord.Embed:
    """Display comprehensive help for commands and game usage."""
    embed = discord.Embed(
        title="🛡️ Backdoors & Breaches Discord Bot — Command Guide",
        description=(
            "A collaborative incident response tabletop simulator powered by Discord slash commands.\n"
            "Simulate security incidents, train your blue team, and investigate cyber attacks!"
        ),
        color=0x2563EB,
    )

    embed.add_field(
        name="🎮 Interactive Game Engine",
        value=(
            f"`{prefix}bnb game setup [deck]` — Set up a game lobby (you become Incident Master)\n"
            f"`{prefix}bnb game join` — Join the current lobby as a defender\n"
            f"`{prefix}bnb game start` — Incident Master starts the exercise\n"
            f"`{prefix}bnb game play` — Play a procedure card and roll d20 on your turn\n"
            f"`{prefix}bnb game hand` — View your private hand (+3 roll bonus cards)\n"
            f"`{prefix}bnb game status` — Check round, cooldowns, and vectors status\n"
            f"`{prefix}bnb game im-panel` — Incident Master private controls and secret vectors\n"
            f"`{prefix}bnb game pass` — Pass your turn to the next player\n"
            f"`{prefix}bnb game end` — End the current game session"
        ),
        inline=False,
    )

    embed.add_field(
        name="🛠️ Tabletop Facilitator Tools",
        value=(
            f"`{prefix}bnb scenario [deck]` — Deal 4 secret attack vectors privately for voice/live games\n"
            f"`{prefix}bnb roll [sides] [modifier]` — Roll dice (e.g. 1d20, d6) with visual embeds\n"
            f"`{prefix}bnb inject [deck]` — Draw a random Inject complication card\n"
            f"`{prefix}bnb consultant [deck]` — Draw a random Consultant expert card"
        ),
        inline=False,
    )

    embed.add_field(
        name="📖 Card Encyclopedia & Decks",
        value=(
            f"`{prefix}bnb card <name>` — Look up any card with full artwork and details\n"
            f"`{prefix}bnb search <query>` — Search cards across all 10 expansions\n"
            f"`{prefix}bnb decks` — List all loaded decks and card counts\n"
            f"`{prefix}bnb rules` — Quick reference guide on B&B mechanics and attack chains"
        ),
        inline=False,
    )

    embed.set_footer(text=FOOTER_TEXT)
    return embed


def create_rules_embed() -> discord.Embed:
    """Display quick rules reference for Backdoors & Breaches."""
    embed = discord.Embed(
        title="📜 Backdoors & Breaches — Quick Reference Rules",
        description=(
            "Backdoors & Breaches is a tabletop incident response card game created by **Black Hills Information Security**.\n"
            "The goal of the defenders is to discover and mitigate all **4 attack vectors** before time runs out!"
        ),
        color=0xF59E0B,
    )

    embed.add_field(
        name="🎯 The 4 Attack Vectors",
        value=(
            "1. 🎯 **Initial Compromise:** How the adversary gained their initial foothold.\n"
            "2. 🔀 **Pivot & Escalate:** How they moved laterally and gained administrator privileges.\n"
            "3. ⚓ **Persistence:** How they maintained access across system restarts.\n"
            "4. 📡 **C2 & Exfiltration:** How they communicate and exfiltrate confidential data."
        ),
        inline=False,
    )

    embed.add_field(
        name="🎲 Dice Rolls & Mechanics",
        value=(
            "• Defenders roll a **20-sided die (d20)** when executing a procedure.\n"
            "• **Success Threshold:** A total roll of **11 or higher** is a SUCCESS.\n"
            "• **Hand Bonus:** Playing a procedure card from your hand gives **+3 to the roll**.\n"
            "• **Natural 20:** Critical Success! Automatically succeeds and uncovers a vector.\n"
            "• **Natural 1:** Critical Failure! Immediately draws an Inject card and puts procedure on cooldown."
        ),
        inline=False,
    )

    embed.add_field(
        name="⚠️ Injects & Cooldowns",
        value=(
            "• When a procedure fails, it goes on **cooldown for 2 turns**.\n"
            "• Every **3 consecutive failed rolls** triggers an **Inject** card.\n"
            "• Injects introduce real-world obstacles, outages, or sudden breakthroughs!"
        ),
        inline=False,
    )

    embed.set_footer(text=FOOTER_TEXT)
    return embed
