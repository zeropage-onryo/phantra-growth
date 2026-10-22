"""What the bot offers, and the rules around it (2026-10-22). No Discord
and no HTTP in here: `flow.py` and `bot.py` call these with what they
were handed, and the tests call them directly.

- `free_looks(rows)`: the rows of the effects table the bot may offer --
  priced at 0 AND on the allowlist (`api.ALLOWLIST`). A row the API
  prices above 0 is never offered even if its id is on the list; a row
  off the list is never offered even at 0. `fallback_looks()` is the list
  itself, for when the API cannot be read (the quote still gates the run).
- `check_clip(size, seconds)`: the 100 MB / 15 s limits, in words.
- `DailyCap`: per-user, in memory and in the store, by UTC day.
- `open_link(base, guild_id, look)`: "Open in Phantra" with the per-server
  tracking parameters `?src=discord&server=<guild id>`.
"""
from __future__ import annotations

from typing import Iterable, Optional
from urllib.parse import urlencode

from .api import ALLOWLIST, BUNDLE_ID, FREE_LOOK_IDS
from .config import MAX_BYTES, MAX_SECONDS

LOOK_LABELS = {
    "film_grade": "Film Grade",
    "noir": "Noir",
    "flash_2000s": "2000s Flash",
    "crash_zoom": "Crash-Zoom Hook",
    "vertical_ready": "Vertical Ready",
    "make_it_pro": "Make It Pro",
}


def _is_free(row: dict) -> bool:
    """A row is free when the API says so: `credits` of 0 (the gallery's
    number) or a `free` flag. None (price depends on the clip) is NOT
    free: the quote decides, and the bot never offers what it cannot
    promise."""
    if row.get("free") is True:
        return True
    credits = row.get("credits")
    return credits is not None and int(credits) == 0


def free_looks(rows: Iterable[dict]) -> list[dict]:
    """The offerable rows, in allowlist order: {id, label, bundle}."""
    by_id = {str(r.get("id") or ""): r for r in rows if isinstance(r, dict)}
    out = []
    for name in ALLOWLIST:
        row = by_id.get(name)
        if row is not None and _is_free(row):
            out.append({"id": name, "label": str(row.get("label") or LOOK_LABELS[name]),
                        "bundle": name == BUNDLE_ID})
    return out


def fallback_looks() -> list[dict]:
    """The allowlist as rows, for when the table cannot be read."""
    return [{"id": n, "label": LOOK_LABELS[n], "bundle": n == BUNDLE_ID} for n in ALLOWLIST]


def single_looks(rows: list[dict]) -> list[dict]:
    """The dropdown for /look: the five looks, never the bundle."""
    return [r for r in rows if r["id"] in FREE_LOOK_IDS]


def check_clip(size_bytes: Optional[int], seconds: Optional[float]) -> Optional[str]:
    """None when the clip is within limits, else the refusal in words.
    Size is checked first (Discord says it before any download); a length
    nobody could measure is a refusal too, never a pass."""
    if size_bytes is None or size_bytes > MAX_BYTES:
        mb = MAX_BYTES // (1024 * 1024)
        return (f"That clip is over {mb} MB. Trim or compress it and try again."
                if size_bytes is not None else "I could not read the clip's size.")
    if seconds is None:
        return "I could not measure the clip's length, so I did not run it."
    if seconds > MAX_SECONDS:
        return (f"That clip is {seconds:.1f}s long; the bot takes up to "
                f"{MAX_SECONDS:.0f}s. Trim it and try again.")
    return None


class DailyCap:
    """How many looks one person gets a day. The store is the memory that
    survives a restart; the dict is the fast path."""

    def __init__(self, limit: int, store=None):
        self.limit = int(limit)
        self.store = store
        self._memory: dict[tuple[str, str], int] = {}

    def used(self, user_id, day: str) -> int:
        key = (str(user_id), day)
        if key not in self._memory:
            self._memory[key] = self.store.daily_count(str(user_id), day) if self.store else 0
        return self._memory[key]

    def allows(self, user_id, day: str) -> bool:
        return self.used(user_id, day) < self.limit

    def count(self, user_id, day: str) -> int:
        """One use, counted. Returns the new count."""
        n = self.store.bump(str(user_id), day) if self.store else self.used(user_id, day) + 1
        self._memory[(str(user_id), day)] = n
        return n

    def left(self, user_id, day: str) -> int:
        return max(0, self.limit - self.used(user_id, day))


def open_link(base: str, guild_id, look: Optional[str] = None) -> str:
    """The "Open in Phantra" address: the studio, with where it came from.
    `server` is the guild id, so a server's clicks can be counted; nothing
    about the person is in it."""
    params = {"src": "discord", "server": str(guild_id) if guild_id is not None else "dm"}
    if look:
        params["look"] = look
    return f"{base.rstrip('/')}?{urlencode(params)}"
