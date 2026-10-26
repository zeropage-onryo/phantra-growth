# phantra-growth

The parts of Phantra that live out on other platforms and bring people in.
They are clients of the Phantra API (`https://api.phantra.ai`), the same way
the plugins are: nothing here imports the studio's code, and nothing in the
studio imports this.

Moved out of the studio repo (`zeropage-onryo/phantra-ai`, `bots/`) on
2026-10-22 with its history. The build notes are in
[`docs/tasks/task-bots.md`](docs/tasks/task-bots.md).

| Folder | What it is | Status |
|---|---|---|
| [`bots/discord/`](bots/discord/README.md) | A public Discord app: `/look` and `/makeitpro` run Phantra's **free** looks on a clip dropped into a channel. | Built and tested against a fake API. Never run against Discord. |
| [`bots/reddit_listener/`](bots/reddit_listener/README.md) | A **read-only** listener: watches six subreddits for "I need what Phantra does" posts and alerts a person. Never posts, comments, votes or messages. | Built and tested against fixtures. Never run against Reddit. |
| `bots/common/` | The shared SQLite store (seen posts, daily caps, welcomed members). | |

Later: a Devvit app for r/phantra, and growth agents, each in a folder of its
own.

## Setup

    python -m venv venv
    venv/bin/pip install -r bots/requirements.txt pytest
    cp .env.example .env      # fill in on the host that runs the bot; never commit it

Run one:

    venv/bin/python -m bots.reddit_listener --once     # one cycle; drop --once to run every 5 min
    venv/bin/python -m bots.discord

Each bot reads its settings from the environment by name; `.env.example`
lists every one, with empty values.

## Tests

    venv/bin/python -m pytest -q

Tests block all network access (`bots/conftest.py`) and clear every bot
setting, so a run with real credentials in the environment still touches
nothing. The Discord wiring test needs `discord.py` installed (it is in
`bots/requirements.txt`) and the clip checks need `ffmpeg`/`ffprobe` on PATH;
both skip with a reason otherwise. CI installs both, so neither skips there.

## Rules every bot here keeps

- **Free or read-only.** The Discord bot runs only looks the API prices at 0
  credits, and sends `expect_credits: 0` so a price change is refused. The
  Reddit listener cannot write to Reddit at all.
- **No unasked messages.** One welcome DM on join (switchable off), never
  repeated; everything else answers a command.
- **Secrets by name only.** Values live on the bot's host, never in the repo
  (a test checks for token-shaped strings).

## Going live on Fly (the Discord bot)

Needs the studio's PR #503 (the bot's door) merged and deployed, and
`PHANTRA_FREE_LOOKS=1` on `phantra-api`.

1. **Discord app** (discord.com/developers/applications): New Application
   "Phantra Looks" -> Bot -> Reset Token (keep it in your password manager).
   Installation: Guild Install on, User Install off, scopes `bot` +
   `applications.commands`, the permissions in `bots/discord/README.md`.
   Bot -> Privileged Gateway Intents: **Server Members Intent** on (the
   welcome DM). Install it on your server with the portal's install link.
2. **Phantra sign-in**: `python -m bots.discord pair`, approve the code at
   phantra.ai/studio/link in the workspace the bot should use, copy the token.
3. **Fly** (from this folder):

       fly launch --copy-config --no-deploy        # keep fly.toml; rename `app` if taken
       fly volumes create growth_state --size 1 --region iad
       fly secrets set DISCORD_BOT_TOKEN=... PHANTRA_BOT_API_KEY=...
       fly deploy
       fly logs                                    # "phantra bot ready as ..."

About $4/month (one shared-cpu-1x 512 MB machine and a 1 GB volume). The
Reddit listener joins the same app once Reddit approves API access: see the
comment in `fly.toml`.
