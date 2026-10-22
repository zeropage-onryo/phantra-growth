"""The two commands and the one welcome, written against DUCK-TYPED
Discord objects (2026-10-22). `bot.py` hands in the real ones; the tests
hand in fakes, so the whole flow -- cap, limits, the free-only rule, the
thread, the link, the single welcome -- is tested without discord.py.

What the flow expects of what it is handed:
  interaction: .user.id, .user.display_name, .guild_id,
               await .response.send_message(text, ephemeral=...),
               await .response.defer(), await .followup.send(text) -> message
  message:     await .create_thread(name=...) -> thread
  thread:      await .send(content=..., file=...)
  attachment:  .filename, .size, .content_type, await .read() -> bytes
  member:      .id, await .send(text)
"""
from __future__ import annotations

import asyncio
import io
import time
from typing import Any, Awaitable, Callable, Optional

from ..common.store import LocalStore, today
from . import clipcheck
from .api import APIError, JobFailed, NotFree, PhantraAPI
from .config import Settings
from .looks import LOOK_LABELS, DailyCap, check_clip, fallback_looks, free_looks, open_link, single_looks

WELCOME_TEXT = (
    "Hi! I'm the Phantra bot. Drop a clip (up to 15s, 100 MB) with `/look` and pick a look, "
    "or `/makeitpro` for the full pass -- both free. The result lands in a thread with an "
    "\"Open in Phantra\" link. This is the only message I'll ever send you directly."
)
LOOKS_TTL = 600.0            # how long the free list is kept before /api/effects is re-read
POST_MAX_BYTES = 25 * 1024 * 1024   # above this the thread gets the link, not the file


def _bytes_file(data: bytes, filename: str):
    """The default `make_file`: a (filename, bytes) pair. bot.py replaces
    it with discord.File."""
    return (filename, io.BytesIO(data))


async def _to_thread(fn, *args):
    return await asyncio.to_thread(fn, *args)


class Services:
    """Everything a command needs, in one bag, so the flow has one
    parameter and the tests one place to fake."""

    def __init__(self, settings: Settings, api: PhantraAPI, store: Optional[LocalStore] = None,
                 *, probe: Callable[[bytes, str], Optional[float]] = clipcheck.probe_seconds,
                 make_file: Callable[[bytes, str], Any] = _bytes_file,
                 to_thread: Callable[..., Awaitable[Any]] = _to_thread,
                 clock: Callable[[], float] = time.monotonic):
        self.settings = settings
        self.api = api
        self.store = store
        self.cap = DailyCap(settings.daily_cap, store)
        self.probe = probe
        self.make_file = make_file
        self.to_thread = to_thread
        self.clock = clock
        self._looks: list[dict] = []
        self._looks_read_at: Optional[float] = None
        self.looks_from_fallback = False

    @classmethod
    def from_settings(cls, settings: Settings) -> "Services":
        from pathlib import Path
        api = PhantraAPI(settings.api_base, settings.api_key, auth=settings.api_auth)
        store = LocalStore(Path(settings.state_dir) / "discord.sqlite")
        return cls(settings, api, store)

    def offered(self, *, refresh: bool = False) -> list[dict]:
        """The looks the bot offers right now: the free, allowlisted rows
        of /api/effects, re-read every LOOKS_TTL seconds; the allowlist
        itself when the API cannot be read (the quote still gates the
        run, so a look that has stopped being free is refused there)."""
        now = self.clock()
        stale = self._looks_read_at is None or now - self._looks_read_at >= LOOKS_TTL
        if refresh or stale:
            try:
                rows = self.api.effects()
                self._looks = free_looks(rows)
                self.looks_from_fallback = False
            except Exception:                                   # noqa: BLE001
                self._looks = fallback_looks()
                self.looks_from_fallback = True
            self._looks_read_at = now
        return list(self._looks)

    def single_looks(self) -> list[dict]:
        return single_looks(self.offered())

    def find_look(self, look_id: str) -> Optional[dict]:
        want = (look_id or "").strip().lower()
        for row in self.offered():
            if row["id"] == want or row["label"].lower() == want:
                return row
        return None


async def _say(interaction, text: str) -> None:
    """A private answer to the person who asked: before the run it is the
    interaction's response, after `defer` it is a followup."""
    resp = interaction.response
    done = getattr(resp, "is_done", None)
    if done is not None and done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await resp.send_message(text, ephemeral=True)


async def run_look_command(interaction, attachment, look_id: str, services: Services) -> dict:
    """`/look` and `/makeitpro`. Returns what happened, for the tests and
    the log: {ok, reason, ...}. Every refusal is said to the person in
    words and runs nothing; a run that fails says "nothing was charged"
    because nothing ever is -- the bot runs looks priced at 0 only."""
    settings = services.settings
    user_id = interaction.user.id
    day = today()
    link = open_link(settings.open_url, interaction.guild_id, look_id)

    look = services.find_look(look_id)
    if look is None:
        await _say(interaction, f"That look is not on the free list right now. "
                                f"The studio has more: {link}")
        return {"ok": False, "reason": "not_offered"}
    label = look["label"]

    if not services.cap.allows(user_id, day):
        await _say(interaction, f"You have used today's {settings.daily_cap} free looks. "
                                f"More tomorrow, or open the studio: {link}")
        return {"ok": False, "reason": "daily_cap"}

    filename = getattr(attachment, "filename", "") or "clip.mp4"
    if not clipcheck.looks_like_video(filename, getattr(attachment, "content_type", None)):
        await _say(interaction, "Attach a video clip (.mp4, .mov or .webm) and try again.")
        return {"ok": False, "reason": "not_video"}

    size = getattr(attachment, "size", None)
    refusal = check_clip(size, 0.0)       # size first: known before any download
    if refusal:
        await _say(interaction, refusal)
        return {"ok": False, "reason": "too_big"}

    await interaction.response.defer()
    data = await attachment.read()
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ".mp4"
    seconds = await services.to_thread(services.probe, data, suffix)
    refusal = check_clip(len(data), seconds)
    if refusal:
        await _say(interaction, refusal)
        return {"ok": False, "reason": "too_long" if seconds is not None else "unmeasured"}

    try:
        result = await services.to_thread(services.api.run_free_look, look["id"], data, filename)
    except NotFree as e:
        await _say(interaction, f"{label} is not free right now ({e.credits} credits), so I "
                                f"did not run it. Run it yourself in the studio: {link}")
        return {"ok": False, "reason": "not_free", "credits": e.credits}
    except (APIError, JobFailed) as e:
        await _say(interaction, f"{label} did not run: {getattr(e, 'message', str(e))}. "
                                f"Nothing was charged.")
        return {"ok": False, "reason": "failed", "error": str(e)}

    n = services.cap.count(user_id, day)
    anchor = await interaction.followup.send(
        f"{label} on `{filename}` is done. {services.cap.limit - n} free look"
        f"{'' if services.cap.limit - n == 1 else 's'} left today.")
    thread = await anchor.create_thread(name=f"{label} · {interaction.user.display_name}")
    content = f"**{label}**\nOpen in Phantra: {link}"
    posted_file = False
    try:
        out = await services.to_thread(services.api.fetch, result["output"])
        if len(out) <= POST_MAX_BYTES:
            stem = filename.rsplit(".", 1)[0]
            await thread.send(content=content,
                              file=services.make_file(out, f"{stem}-{look['id']}.mp4"))
            posted_file = True
    except (APIError, JobFailed):
        pass
    if not posted_file:
        await thread.send(content=f"{content}\n{result['output']}")
    return {"ok": True, "look": look["id"], "handle": result["handle"], "output": result["output"],
            "link": link, "posted_file": posted_file, "used_today": n}


async def welcome_member(member, services: Services) -> bool:
    """The ONE direct message the bot ever sends: on join, if the flag is
    on, and only once per person ever (marked BEFORE sending, so a DM the
    person's settings refuse is still never retried). True when sent."""
    if not services.settings.welcome_dm:
        return False
    store = services.store
    if store is None:
        return False
    if not store.add("welcomed", str(member.id)):
        return False
    try:
        await member.send(WELCOME_TEXT)
    except Exception:                                           # noqa: BLE001
        return False
    return True


__all__ = ["Services", "run_look_command", "welcome_member", "WELCOME_TEXT", "LOOK_LABELS"]
