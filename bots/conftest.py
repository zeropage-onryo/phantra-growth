"""The network guard for every test under bots/ (2026-10-22).

A copy of `tests/conftest.py`'s `no_network` fixture, not an import of it:
that module pulls in the app, the throwaway database and `.env` posture,
none of which a bot test needs. The guard is the same wall for the same
reason -- a billed call once ran inside a passing test, four times -- and
it is the reason a bot test can be run with real Discord, Reddit or
Phantra credentials in the environment and still touch nothing.
"""
import socket

import pytest


class NetworkUseInTest(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    def blocked(*args, **kwargs):
        raise NetworkUseInTest(
            f"{request.node.nodeid} tried to open a network connection. "
            "A bot test talks to a fake client; if one reached the socket, a "
            "monkeypatch is patching a function the code under test no longer calls."
        )

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture(autouse=True)
def no_bot_credentials(monkeypatch):
    """Shipped defaults, not this machine's .env: a test that is ABOUT a
    setting sets it itself."""
    for name in ("DISCORD_BOT_TOKEN", "PHANTRA_API_BASE", "PHANTRA_BOT_API_KEY",
                 "PHANTRA_BOT_STATE_DIR", "PHANTRA_BOT_DAILY_CAP", "PHANTRA_BOT_WELCOME_DM",
                 "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT",
                 "REDDIT_ALERT_WEBHOOK_URL", "REDDIT_INTENT_PHRASES", "REDDIT_SUBREDDITS",
                 "REDDIT_ALERT_SMTP_HOST", "REDDIT_ALERT_SMTP_PORT", "REDDIT_ALERT_SMTP_USER",
                 "REDDIT_ALERT_SMTP_PASSWORD", "REDDIT_ALERT_FROM", "REDDIT_ALERT_TO"):
        monkeypatch.delenv(name, raising=False)
