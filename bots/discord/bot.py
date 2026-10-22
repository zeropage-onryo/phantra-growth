"""The discord.py wiring (2026-10-22). Imported lazily: `build()` imports
`discord` so the rest of the package, and its tests, load without the
library. No guild id anywhere: the commands are global, the app is
installed by anyone through the install link in README.md.
"""
from __future__ import annotations

import io
import sys

from . import flow
from .config import Settings


def build(settings: Settings, services: flow.Services):
    import discord
    from discord import app_commands

    intents = discord.Intents.default()
    # the welcome needs the privileged Server Members intent; off = no joins seen
    intents.members = settings.welcome_dm
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    def make_file(data: bytes, filename: str):
        return discord.File(io.BytesIO(data), filename=filename)

    services.make_file = make_file

    @tree.command(name="look", description="A free Phantra look on your clip (up to 15s, 100 MB)")
    @app_commands.describe(clip="The clip (.mp4, .mov or .webm)", look="Which look")
    async def look(interaction: discord.Interaction, clip: discord.Attachment, look: str):
        await flow.run_look_command(interaction, clip, look, services)

    @look.autocomplete("look")
    async def look_choices(interaction: discord.Interaction, current: str):
        want = (current or "").lower()
        return [app_commands.Choice(name=row["label"], value=row["id"])
                for row in services.single_looks() if want in row["label"].lower()][:25]

    @tree.command(name="makeitpro", description="Make It Pro: the free bundle on your clip")
    @app_commands.describe(clip="The clip (.mp4, .mov or .webm)")
    async def makeitpro(interaction: discord.Interaction, clip: discord.Attachment):
        await flow.run_look_command(interaction, clip, "make_it_pro", services)

    @client.event
    async def on_ready():
        await tree.sync()
        print(f"phantra bot ready as {client.user}; offering "
              f"{[r['id'] for r in services.offered()]}", file=sys.stderr)

    @client.event
    async def on_member_join(member: discord.Member):
        await flow.welcome_member(member, services)

    return client


def main() -> int:
    settings = Settings.from_env()
    missing = settings.missing()
    if missing:
        print(f"not started: set {', '.join(missing)} in the environment", file=sys.stderr)
        return 2
    services = flow.Services.from_settings(settings)
    client = build(settings, services)
    client.run(settings.token, log_handler=None)
    return 0
