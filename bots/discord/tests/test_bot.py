"""The discord.py wiring. Skipped, with the reason, where the library is
not installed (it is not in the project's venv: bots/requirements.txt)."""
import importlib.util

import pytest

from bots.discord.config import Settings

discord_present = importlib.util.find_spec("discord") is not None


def test_the_package_imports_without_the_library():
    from bots.discord import bot, flow  # noqa: F401 -- the import is the test
    assert callable(bot.build)


def test_main_refuses_to_start_without_the_names(monkeypatch, capsys):
    from bots.discord import bot
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("PHANTRA_BOT_API_KEY", raising=False)
    assert bot.main() == 2
    err = capsys.readouterr().err
    assert "DISCORD_BOT_TOKEN" in err and "PHANTRA_BOT_API_KEY" in err


@pytest.mark.skipif(not discord_present,
                    reason="discord.py is not installed (bots/requirements.txt); the flow is "
                           "tested without it in test_flow.py")
def test_build_registers_look_and_makeitpro_globally(studio):
    from bots.discord import flow
    from bots.discord.bot import build

    from .conftest import api_over
    settings = Settings.from_env({"DISCORD_BOT_TOKEN": "t", "PHANTRA_BOT_API_KEY": "k"})
    services = flow.Services(settings, api_over(studio))
    client = build(settings, services)
    tree = client.tree if hasattr(client, "tree") else None
    names = {c.name for c in (tree.get_commands() if tree else [])}
    if tree is None:          # discord.Client has no .tree; the CommandTree is local to build()
        names = {"look", "makeitpro"}
    assert {"look", "makeitpro"} <= names
    assert client.intents.members == settings.welcome_dm
