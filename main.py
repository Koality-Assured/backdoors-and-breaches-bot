"""
Main entry point for the Backdoors & Breaches Discord bot.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import discord
from discord import Activity, ActivityType
from discord.ext import commands

from bnb.cogs import AdminCog, AssistantCog, CardsCog, GameCog
from bnb.config import Settings
from bnb.deck_loader import DeckLoader
from bnb.engine import GameManager


def setup_logging(level_name: str) -> None:
    """Configure formatted console logging."""
    numeric_level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def main() -> None:
    """Initialize systems, register cogs, and run the bot."""
    settings = Settings.load()
    setup_logging(settings.log_level)
    logger = logging.getLogger("bnb.main")

    logger.info("Starting Backdoors & Breaches Discord Bot...")

    if not settings.token:
        logger.error(
            "CRITICAL: No Discord bot token provided! "
            "Please set DISCORD_TOKEN in your environment or create a .env file."
        )
        sys.exit(1)

    # 1. Initialize Deck Loader and index all cards
    deck_loader = DeckLoader(decks_dir=settings.decks_dir)
    deck_loader.load_all_decks()

    if not deck_loader.list_decks():
        logger.warning(
            "No decks found in %s! Please ensure deck folders exist.",
            settings.decks_dir,
        )

    # 2. Initialize Game Engine Manager
    game_manager = GameManager()

    # 3. Configure Discord Bot Client
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True

    bot = commands.Bot(
        command_prefix=commands.when_mentioned_or(settings.command_prefix),
        intents=intents,
        help_command=None,  # Custom /bnbhelp implemented in AdminCog
    )

    # 4. Register Cogs
    await bot.add_cog(GameCog(bot, deck_loader, game_manager, settings))
    await bot.add_cog(AssistantCog(bot, deck_loader, settings))
    await bot.add_cog(CardsCog(bot, deck_loader, settings))
    await bot.add_cog(AdminCog(bot, deck_loader, settings))

    @bot.event
    async def on_ready() -> None:
        logger.info("Bot logged in as: %s (ID: %s)", bot.user.name, bot.user.id)

        # Set Rich Presence
        activity = Activity(
            type=ActivityType.playing,
            name=f"Backdoors & Breaches | {settings.command_prefix}bnbhelp",
        )
        await bot.change_presence(activity=activity)

        # Sync Application Commands
        try:
            if settings.dev_guild_id:
                guild = discord.Object(id=settings.dev_guild_id)
                bot.tree.copy_global_to(guild=guild)
                synced = await bot.tree.sync(guild=guild)
                logger.info("Synced %d command(s) to development guild %s", len(synced), settings.dev_guild_id)
            else:
                synced = await bot.tree.sync()
                logger.info("Globally synced %d slash command(s)", len(synced))
        except Exception as exc:
            logger.error("Failed to sync application commands: %s", exc)

        # Generate OAuth2 Invitation URL
        invite_url = discord.utils.oauth_url(
            bot.user.id,
            permissions=discord.Permissions(
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_messages=True,
                read_message_history=True,
                add_reactions=True,
                use_application_commands=True,
            ),
            scopes=["bot", "applications.commands"],
        )
        logger.info("Invite URL: %s", invite_url)

    # 5. Start Bot
    try:
        await bot.start(settings.token)
    except discord.LoginFailure:
        logger.error("Authentication failed: Invalid Discord token provided.")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Bot shutting down...")
    finally:
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
