"""A small SQLite store for a bot's own bookkeeping (2026-10-22).

Three questions a bot asks that must survive a restart: how many times
has this person used it today (the Discord daily cap), has this person
already had the one welcome message (never repeated), and has this post
already been seen (the Reddit listener's de-duplication). One file under a
configurable directory, stdlib only, safe to delete: nothing in it is a
record anybody paid for.
"""
from __future__ import annotations

import datetime as _dt
import os
import sqlite3
from pathlib import Path
from typing import Optional

DEFAULT_DIR_ENV = "PHANTRA_BOT_STATE_DIR"


def state_dir(default: str = "bots/state") -> Path:
    """Where the stores live: `PHANTRA_BOT_STATE_DIR`, else `bots/state/`
    under the working directory (gitignored)."""
    return Path(os.environ.get(DEFAULT_DIR_ENV) or default)


def today() -> str:
    """The cap's day, in UTC, as YYYY-MM-DD. UTC so a bot restarted on a
    host in another zone counts the same day."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


class LocalStore:
    """`daily_count` / `bump` for a per-key daily counter, `has` / `add`
    for named sets. ``":memory:"`` is a store that forgets on close."""

    def __init__(self, path: str | os.PathLike = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS daily "
                         "(key TEXT NOT NULL, day TEXT NOT NULL, n INTEGER NOT NULL, "
                         "PRIMARY KEY (key, day))")
        self._db.execute("CREATE TABLE IF NOT EXISTS sets "
                         "(name TEXT NOT NULL, member TEXT NOT NULL, added TEXT NOT NULL, "
                         "PRIMARY KEY (name, member))")
        self._db.commit()

    # -- the daily counter ---------------------------------------------
    def daily_count(self, key: str, day: Optional[str] = None) -> int:
        row = self._db.execute("SELECT n FROM daily WHERE key = ? AND day = ?",
                               (str(key), day or today())).fetchone()
        return int(row[0]) if row else 0

    def bump(self, key: str, day: Optional[str] = None) -> int:
        """Count one more use and return the new count."""
        day = day or today()
        self._db.execute("INSERT INTO daily (key, day, n) VALUES (?, ?, 1) "
                         "ON CONFLICT (key, day) DO UPDATE SET n = n + 1", (str(key), day))
        self._db.commit()
        return self.daily_count(key, day)

    # -- named sets ------------------------------------------------------
    def has(self, name: str, member: str) -> bool:
        row = self._db.execute("SELECT 1 FROM sets WHERE name = ? AND member = ?",
                               (name, str(member))).fetchone()
        return row is not None

    def add(self, name: str, member: str) -> bool:
        """Add; True when it was new."""
        if self.has(name, member):
            return False
        self._db.execute("INSERT INTO sets (name, member, added) VALUES (?, ?, ?)",
                         (name, str(member), _dt.datetime.now(_dt.timezone.utc).isoformat()))
        self._db.commit()
        return True

    def close(self) -> None:
        self._db.close()
