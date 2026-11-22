from __future__ import annotations

import pytest

from investwatch.config import ConfigError, get_settings


def test_browser_user_agent_fails_with_one_readable_line(monkeypatch: pytest.MonkeyPatch) -> None:
    # A pre-#17 .env could disguise the crawler as a browser; that is refused at startup.
    monkeypatch.setenv(
        "COLLECTOR_USER_AGENTS", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0"
    )
    get_settings.cache_clear()
    with pytest.raises(ConfigError) as caught:
        get_settings()
    message = str(caught.value)
    assert "\n" not in message
    assert "COLLECTOR_USER_AGENTS" in message
    assert "InvestWatchBot" in message
    assert ".env.example" in message


def test_bot_user_agents_are_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLLECTOR_USER_AGENTS", "InvestWatchBot/1.0 (+https://example.org)")
    get_settings.cache_clear()
    assert get_settings().user_agents == ["InvestWatchBot/1.0 (+https://example.org)"]
