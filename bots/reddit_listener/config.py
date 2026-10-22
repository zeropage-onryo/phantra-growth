"""Settings by environment name; the defaults the brief fixed (2026-10-22)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

CLIENT_ID_ENV = "REDDIT_CLIENT_ID"
CLIENT_SECRET_ENV = "REDDIT_CLIENT_SECRET"
USER_AGENT_ENV = "REDDIT_USER_AGENT"
WEBHOOK_ENV = "REDDIT_ALERT_WEBHOOK_URL"
SUBREDDITS_ENV = "REDDIT_SUBREDDITS"
PHRASES_ENV = "REDDIT_INTENT_PHRASES"
SMTP_HOST_ENV = "REDDIT_ALERT_SMTP_HOST"
SMTP_PORT_ENV = "REDDIT_ALERT_SMTP_PORT"
SMTP_USER_ENV = "REDDIT_ALERT_SMTP_USER"
SMTP_PASSWORD_ENV = "REDDIT_ALERT_SMTP_PASSWORD"
MAIL_FROM_ENV = "REDDIT_ALERT_FROM"
MAIL_TO_ENV = "REDDIT_ALERT_TO"
STATE_DIR_ENV = "PHANTRA_BOT_STATE_DIR"

DEFAULT_SUBREDDITS = ("aivideo", "VideoEditing", "filmmakers", "SaaS", "SideProject", "NewTubers")

# The phrases the brief named, plus near neighbours. Matched case- and
# whitespace-insensitively as substrings of title + body (matcher.py).
DEFAULT_PHRASES = (
    "make my video look cinematic",
    "make my videos look cinematic",
    "best ai video tool",
    "best ai video generator",
    "higgsfield alternative",
    "runway alternative",
    "need a product demo video",
    "need a demo video",
    "product demo video",
    "ai video for my product",
    "cinematic look",
    "color grade my",
)


def _split(value: str, sep: str) -> list[str]:
    return [p.strip() for p in (value or "").split(sep) if p.strip()]


@dataclass(frozen=True)
class Settings:
    client_id: str
    client_secret: str
    user_agent: str
    webhook_url: str
    subreddits: tuple[str, ...]
    phrases: tuple[str, ...]
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    mail_from: str
    mail_to: tuple[str, ...]
    state_dir: str
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, env=None) -> "Settings":
        env = os.environ if env is None else env
        port = env.get(SMTP_PORT_ENV, "").strip()
        subs = tuple(_split(env.get(SUBREDDITS_ENV, ""), ",")) or DEFAULT_SUBREDDITS
        phrases = DEFAULT_PHRASES + tuple(_split(env.get(PHRASES_ENV, ""), "|"))
        return cls(
            client_id=env.get(CLIENT_ID_ENV, "").strip(),
            client_secret=env.get(CLIENT_SECRET_ENV, "").strip(),
            user_agent=env.get(USER_AGENT_ENV, "").strip(),
            webhook_url=env.get(WEBHOOK_ENV, "").strip(),
            subreddits=subs,
            phrases=phrases,
            smtp_host=env.get(SMTP_HOST_ENV, "").strip(),
            smtp_port=int(port) if port.isdigit() else 587,
            smtp_user=env.get(SMTP_USER_ENV, "").strip(),
            smtp_password=env.get(SMTP_PASSWORD_ENV, ""),
            mail_from=env.get(MAIL_FROM_ENV, "").strip(),
            mail_to=tuple(_split(env.get(MAIL_TO_ENV, ""), ",")),
            state_dir=env.get(STATE_DIR_ENV, "").strip() or "bots/state",
        )

    def missing(self) -> list[str]:
        """The NAMES needed to read Reddit at all."""
        return [name for name, value in ((CLIENT_ID_ENV, self.client_id),
                                         (CLIENT_SECRET_ENV, self.client_secret),
                                         (USER_AGENT_ENV, self.user_agent)) if not value]

    def alert_targets(self) -> list[str]:
        out = []
        if self.webhook_url:
            out.append("webhook")
        if self.smtp_host and self.mail_from and self.mail_to:
            out.append("email")
        return out
