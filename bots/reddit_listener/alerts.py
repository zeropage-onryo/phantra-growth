"""Where an alert goes (2026-10-22): a Discord channel webhook, an email
over SMTP, or stdout. Each takes a formatted alert and sends it; none of
them touches Reddit. The HTTP client and the SMTP class are injectable
so the tests send nothing.
"""
from __future__ import annotations

import smtplib
import sys
from email.message import EmailMessage
from typing import Any, Callable, Optional

import httpx


def format_alert(post: dict, phrases: list[str]) -> str:
    body = (post.get("selftext") or "").strip().replace("\n", " ")
    if len(body) > 280:
        body = body[:277] + "..."
    lines = [f"r/{post.get('subreddit')} · u/{post.get('author') or '[deleted]'} · "
             f"matched: {', '.join(phrases)}",
             f"**{post.get('title', '').strip()}**",
             post.get("link", "")]
    if body:
        lines.insert(2, body)
    return "\n".join(lines)


class StdoutAlert:
    name = "stdout"

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout

    def send(self, text: str) -> bool:
        print(text + "\n", file=self.stream)
        return True


class WebhookAlert:
    """One Discord channel webhook (its URL by env name, never in the
    repo). A webhook posts into ONE channel the server's admin created it
    for; it cannot DM anyone or post elsewhere."""
    name = "webhook"

    def __init__(self, url: str, client: Optional[httpx.Client] = None):
        self.url = url
        self._client = client or httpx.Client(timeout=20.0)

    def send(self, text: str) -> bool:
        resp = self._client.post(self.url, json={"content": text[:1990],
                                                 "allowed_mentions": {"parse": []}})
        return resp.status_code < 300


class EmailAlert:
    name = "email"

    def __init__(self, host: str, port: int, user: str, password: str, sender: str,
                 recipients: list[str], smtp: Callable[..., Any] = smtplib.SMTP):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender, self.recipients = sender, list(recipients)
        self._smtp = smtp

    def send(self, text: str, subject: str = "Phantra: a Reddit post worth a look") -> bool:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, ", ".join(self.recipients), subject
        msg.set_content(text)
        with self._smtp(self.host, self.port, timeout=20) as s:
            try:
                s.starttls()
            except Exception:                                   # noqa: BLE001
                pass                                            # a server without TLS
            if self.user:
                s.login(self.user, self.password)
            s.send_message(msg)
        return True
