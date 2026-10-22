"""Phantra's bots (2026-10-22, docs/tasks/task-bots.md).

Two small programs that live beside the studio and talk to it only over
HTTP: the Discord bot (`bots/discord/`, a public installable app that runs
the FREE looks on a dropped clip) and the Reddit listener
(`bots/reddit_listener/`, read-only: it watches for intent and alerts a
person, and never posts, comments, votes or messages).

Nothing here imports `src/` or `app/`: a bot is a client of the API, as the
plugins are, and runs on a host of its own. Credentials are read from the
environment by name and never written down (`.env.example` lists the
names with empty values). Tests run with
`venv/bin/python -m pytest bots -q` against mocked clients and a socket
guard (`bots/conftest.py`), so a bot test can never reach the network.
"""
