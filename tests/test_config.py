"""
Unit tests for configuration loading and validation.
"""

from bnb.config import Settings


def test_default_settings():
    settings = Settings.load(config_path="nonexistent_config.ini")
    assert settings.command_prefix in ("!", "/") or settings.command_prefix == "!"
    assert settings.default_deck == "CoreV2.2"
    assert settings.max_turns == 10
    assert settings.inject_failure_threshold == 3
    assert settings.is_channel_allowed(99999) is True


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "fake_token_12345")
    monkeypatch.setenv("COMMAND_PREFIX", "?")
    monkeypatch.setenv("DEFAULT_DECK", "Huntress")
    monkeypatch.setenv("MAX_TURNS", "15")
    monkeypatch.setenv("ALLOWED_CHANNELS", "111,222")

    settings = Settings.load(config_path="nonexistent_config.ini")
    assert settings.token == "fake_token_12345"
    assert settings.command_prefix == "?"
    assert settings.default_deck == "Huntress"
    assert settings.max_turns == 15
    assert settings.allowed_channel_ids == [111, 222]
    assert settings.is_channel_allowed(111) is True
    assert settings.is_channel_allowed(333) is False
