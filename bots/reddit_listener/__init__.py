"""The Phantra Reddit listener (2026-10-22, docs/tasks/task-bots.md).

READ-ONLY. It watches a handful of subreddits for sentences that mean
"I need what Phantra does" and tells a person (email, or a Discord
channel webhook). It never posts, comments, votes, messages or edits:
the PRAW client is wrapped in `facade.ReadOnlyReddit`, which exposes
reading only, and a test asserts no write method is ever called on the
underlying client across a full cycle.

Modules: `config` (env names, the default subreddits and phrases),
`facade` (the read-only wrapper), `matcher` (intent phrases), `alerts`
(email / webhook / stdout), `listener` (one cycle, the loop).
`python -m bots.reddit_listener` runs it; `--once` runs one cycle.
"""
