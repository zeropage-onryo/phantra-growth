"""One cycle, and the loop around it (2026-10-22).

`cycle()` reads the newest posts of each subreddit through the read-only
facade, skips ids already in the store, matches the phrases, marks every
post it saw (seen is seen, matched or not, so a cycle never re-reads a
post), and hands each match to every alerter. It returns what it
matched. It never calls anything but `new_posts` on the facade.
"""
from __future__ import annotations

import sys
import time
from typing import Iterable, Optional

from ..common.store import LocalStore
from . import alerts as alerts_mod
from .config import Settings
from .facade import ReadOnlyReddit, build_client
from .matcher import matches

SEEN = "reddit_seen"


def cycle(reddit: ReadOnlyReddit, subreddits: Iterable[str], phrases: Iterable[str],
          store: LocalStore, alerters: Iterable, *, limit: int = 50,
          log=None) -> list[dict]:
    phrases = list(phrases)
    alerters = list(alerters)
    found: list[dict] = []
    for name in subreddits:
        try:
            posts = reddit.new_posts(name, limit=limit)
        except Exception as e:                                  # noqa: BLE001
            print(f"  r/{name}: could not read ({e.__class__.__name__})", file=log or sys.stderr)
            continue
        for post in posts:
            pid = post.get("id") or ""
            if not pid or store.has(SEEN, pid):
                continue
            store.add(SEEN, pid)
            hit = matches(post, phrases)
            if not hit:
                continue
            text = alerts_mod.format_alert(post, hit)
            sent = []
            for alerter in alerters:
                try:
                    if alerter.send(text):
                        sent.append(alerter.name)
                except Exception as e:                          # noqa: BLE001
                    print(f"  alert via {alerter.name} failed: {e.__class__.__name__}",
                          file=log or sys.stderr)
            found.append({**post, "matched": hit, "alerted": sent})
    return found


def alerters_for(settings: Settings) -> list:
    out: list = []
    if settings.webhook_url:
        out.append(alerts_mod.WebhookAlert(settings.webhook_url))
    if "email" in settings.alert_targets():
        out.append(alerts_mod.EmailAlert(settings.smtp_host, settings.smtp_port,
                                         settings.smtp_user, settings.smtp_password,
                                         settings.mail_from, list(settings.mail_to)))
    if not out:
        out.append(alerts_mod.StdoutAlert())
    return out


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    from pathlib import Path
    ap = argparse.ArgumentParser(prog="python -m bots.reddit_listener",
                                 description="Watch subreddits for intent; read-only; alerts only.")
    ap.add_argument("--once", action="store_true", help="one cycle, then exit")
    ap.add_argument("--interval", type=int, default=300, help="seconds between cycles")
    ap.add_argument("--limit", type=int, default=50, help="newest posts per subreddit")
    args = ap.parse_args(argv)
    settings = Settings.from_env()
    missing = settings.missing()
    if missing:
        print(f"not started: set {', '.join(missing)} in the environment", file=sys.stderr)
        return 2
    reddit = build_client(settings.client_id, settings.client_secret, settings.user_agent)
    store = LocalStore(Path(settings.state_dir) / "reddit.sqlite")
    alerters = alerters_for(settings)
    print(f"listening on {', '.join('r/' + s for s in settings.subreddits)}; alerts via "
          f"{', '.join(a.name for a in alerters)}; never posting", file=sys.stderr)
    while True:
        found = cycle(reddit, settings.subreddits, settings.phrases, store, alerters,
                      limit=args.limit)
        print(f"cycle: {len(found)} match(es)", file=sys.stderr)
        if args.once:
            return 0
        time.sleep(max(60, args.interval))
