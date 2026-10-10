"""
Configuration management for the Backdoors & Breaches Discord bot.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class Settings:
    """Application settings loaded from environment or config file."""
    token: str = ""
    command_prefix: str = "!"
    default_deck: str = "CoreV2.2"
    decks_dir: Path = field(default_factory=lambda: Path("decks"))
    max_turns: int = 10
    inject_failure_threshold: int = 3
    allowed_channel_ids: List[int] = field(default_factory=list)
    dev_guild_id: Optional[int] = None
    log_level: str = "INFO"

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> Settings:
        """
        Load settings from environment variables with fallback to config.ini.
        """
        settings = cls()

        # 1. Check config.ini if it exists
        ini_file = Path(config_path or "config.ini")
        if ini_file.is_file():
            parser = configparser.ConfigParser()
            try:
                parser.read(ini_file, encoding="utf-8")
                if "SETTINGS" in parser:
                    sec = parser["SETTINGS"]
                    settings.token = sec.get("discordtoken", "").strip()
                    settings.command_prefix = sec.get("command_prefix", settings.command_prefix).strip()
                    settings.default_deck = sec.get("default_deck", settings.default_deck).strip()
                    settings.max_turns = sec.getint("max_turns", settings.max_turns)

                    ch = sec.get("channel_id", "").strip()
                    if ch:
                        try:
                            settings.allowed_channel_ids = [int(c.strip()) for c in ch.split(",") if c.strip()]
                        except ValueError:
                            pass
            except Exception:
                pass

        # 2. Environment variables override config.ini
        env_token = os.environ.get("DISCORD_TOKEN") or os.environ.get("BOT_TOKEN")
        if env_token:
            settings.token = env_token.strip()

        env_prefix = os.environ.get("COMMAND_PREFIX")
        if env_prefix:
            settings.command_prefix = env_prefix.strip()

        env_deck = os.environ.get("DEFAULT_DECK")
        if env_deck:
            settings.default_deck = env_deck.strip()

        env_decks_dir = os.environ.get("DECKS_DIR")
        if env_decks_dir:
            settings.decks_dir = Path(env_decks_dir)

        env_max_turns = os.environ.get("MAX_TURNS")
        if env_max_turns and env_max_turns.isdigit():
            settings.max_turns = int(env_max_turns)

        env_inject_thresh = os.environ.get("INJECT_FAILURE_THRESHOLD")
        if env_inject_thresh and env_inject_thresh.isdigit():
            settings.inject_failure_threshold = int(env_inject_thresh)

        env_channels = os.environ.get("ALLOWED_CHANNELS") or os.environ.get("CHANNEL_ID")
        if env_channels:
            try:
                settings.allowed_channel_ids = [
                    int(c.strip()) for c in env_channels.split(",") if c.strip()
                ]
            except ValueError:
                pass

        env_dev_guild = os.environ.get("DEV_GUILD_ID")
        if env_dev_guild and env_dev_guild.strip().isdigit():
            settings.dev_guild_id = int(env_dev_guild.strip())

        env_log_level = os.environ.get("LOG_LEVEL")
        if env_log_level:
            settings.log_level = env_log_level.strip().upper()

        return settings

    def is_channel_allowed(self, channel_id: int) -> bool:
        """Check if games are allowed in this channel ID."""
        if not self.allowed_channel_ids:
            return True
        return channel_id in self.allowed_channel_ids
