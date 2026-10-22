"""The Phantra Discord bot (2026-10-22, docs/tasks/task-bots.md).

A public, installable app: `/look` runs one of the FREE looks on a dropped
clip and `/makeitpro` runs the Make It Pro bundle, each answered as the
finished clip in a thread under the command, with an "Open in Phantra"
link. It talks to the studio only over HTTP (`api.py`), never to a
provider, and only ever runs an effect the API prices at 0 credits.

Modules: `config` (env names), `api` (the HTTP client), `looks` (the free
list, limits, cap, link), `clipcheck` (size and length before any
upload), `flow` (the command, written against duck-typed Discord objects
so it is tested without the library), `bot` (the discord.py wiring,
imported lazily). `python -m bots.discord` runs it.
"""
