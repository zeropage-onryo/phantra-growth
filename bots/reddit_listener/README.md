# The Phantra Reddit listener (read-only)

Watches r/aivideo, r/VideoEditing, r/filmmakers, r/SaaS, r/SideProject and
r/NewTubers for sentences that mean "I need what Phantra does" and tells a
person. Built 2026-10-22 (`docs/tasks/task-bots.md`).

**It never posts, comments, votes, messages, saves or edits.** The PRAW
client is wrapped in `facade.ReadOnlyReddit`, which exposes `new_posts()`
and nothing else (every write name raises by name, nothing passes through,
the object is sealed), and hands back plain dicts so nothing downstream can
reach a PRAW object. `tests/test_read_only.py` runs a whole cycle over a
`MagicMock` client and asserts the only calls were `subreddit(<name>)` and
`.new(limit=...)`. The PRAW client is built with id, secret and user agent
only (no username, no password, no refresh token) and `read_only = True`:
Reddit itself would refuse a write from it.

## Running it

    python -m venv bots/venv && bots/venv/bin/pip install -r bots/requirements.txt
    export REDDIT_CLIENT_ID=... REDDIT_CLIENT_SECRET=... REDDIT_USER_AGENT="phantra-listener/0.1 by u/<you>"
    export REDDIT_ALERT_WEBHOOK_URL=...        # and/or the REDDIT_ALERT_SMTP_* + FROM/TO names
    bots/venv/bin/python -m bots.reddit_listener            # every 5 minutes
    bots/venv/bin/python -m bots.reddit_listener --once     # one cycle

A Reddit "script" app (reddit.com/prefs/apps) gives the id and secret;
Reddit asks for a descriptive user agent. With no alert target configured,
matches print to stdout. Settings, by name, are in `.env.example` under
"the bots". `REDDIT_INTENT_PHRASES` (`|`-separated) adds to the default
phrases; `REDDIT_SUBREDDITS` (comma-separated) replaces the default list.

## What a cycle does

1. `new_posts(sub, limit)` for each subreddit, through the facade.
2. Skip ids already in the store (`bots/state/reddit.sqlite`); mark every
   post seen, matched or not, so nothing is read twice.
3. `matcher.matches(post, phrases)`: case- and whitespace-insensitive
   substrings of title + body.
4. `alerts.format_alert` -> each alerter (`WebhookAlert`: one Discord channel
   webhook, mentions off; `EmailAlert`: SMTP with STARTTLS; `StdoutAlert`).
   A failing alerter is a line on stderr, never a crash.

The text of a post is data: it is quoted in the alert and acted on by
nobody (fixture `1abc03` carries an "ignore previous instructions" line to
hold that in a test).

## Tests

    venv/bin/python -m pytest bots/reddit_listener -q

Fixtures in `tests/fixtures/` are hand-written in the shape PRAW's
`new()` yields (not recorded from Reddit). `praw` is not installed in the
project's venv and is imported only inside `facade.build_client`.
