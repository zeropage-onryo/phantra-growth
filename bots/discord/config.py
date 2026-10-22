"""Every setting the Discord bot reads, by environment name (2026-10-22).

Values are never in the repo: `.env.example` lists the names with empty
values and Mike fills them on the bot's host. `Settings.from_env()` is the
one reader; a missing token is said by name at start, never printed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

TOKEN_ENV = "DISCORD_BOT_TOKEN"
API_BASE_ENV = "PHANTRA_API_BASE"
API_KEY_ENV = "PHANTRA_BOT_API_KEY"
API_AUTH_ENV = "PHANTRA_BOT_API_AUTH"          # cookie (default) | bearer
STATE_DIR_ENV = "PHANTRA_BOT_STATE_DIR"
DAILY_CAP_ENV = "PHANTRA_BOT_DAILY_CAP"
WELCOME_DM_ENV = "PHANTRA_BOT_WELCOME_DM"      # "1" (default) | "0"
OPEN_URL_ENV = "PHANTRA_OPEN_URL"              # where "Open in Phantra" points

DEFAULT_API_BASE = "https://api.phantra.ai"
DEFAULT_OPEN_URL = "https://phantra.ai/studio"
DEFAULT_DAILY_CAP = 5

# The limits a clip is held to BEFORE anything is uploaded.
MAX_SECONDS = 15.0
MAX_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class Settings:
    token: str
    api_base: str
    api_key: str
    api_auth: str
    state_dir: str
    daily_cap: int
    welcome_dm: bool
    open_url: str

    @classmethod
    def from_env(cls, env=None) -> "Settings":
        env = os.environ if env is None else env
        cap = env.get(DAILY_CAP_ENV, "").strip()
        return cls(
            token=env.get(TOKEN_ENV, "").strip(),
            api_base=(env.get(API_BASE_ENV, "").strip() or DEFAULT_API_BASE).rstrip("/"),
            api_key=env.get(API_KEY_ENV, "").strip(),
            api_auth=(env.get(API_AUTH_ENV, "").strip().lower() or "cookie"),
            state_dir=env.get(STATE_DIR_ENV, "").strip() or "bots/state",
            daily_cap=int(cap) if cap.isdigit() else DEFAULT_DAILY_CAP,
            welcome_dm=(env.get(WELCOME_DM_ENV, "1").strip() or "1") != "0",
            open_url=(env.get(OPEN_URL_ENV, "").strip() or DEFAULT_OPEN_URL).rstrip("/"),
        )

    def missing(self) -> list[str]:
        """The NAMES of the settings the bot cannot start without."""
        out = []
        if not self.token:
            out.append(TOKEN_ENV)
        if not self.api_key:
            out.append(API_KEY_ENV)
        return out
