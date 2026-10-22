# The Phantra Discord bot

A public, installable Discord app that runs Phantra's **free looks** on a
clip dropped into a channel. Built 2026-10-22 (`docs/tasks/task-bots.md`).
It is a client of the Phantra API over HTTP and nothing else: no provider
SDK, no `src/` import, no guild-specific code.

## What it does

- `/look clip:<attachment> look:<pick>`: the dropdown lists the free looks
  (Film Grade, Noir, 2000s Flash, Crash-Zoom Hook, Vertical Ready), read from
  `GET /api/effects` at runtime and kept only where the API prices the row at
  **0 credits** and the id is on the bot's allowlist (`api.ALLOWLIST`). If the
  table cannot be read, the allowlist itself is offered; the quote still gates
  the run.
- `/makeitpro clip:<attachment>`: the `make_it_pro` bundle through the same door.
- The result is posted **as the clip** in a thread under the bot's reply to the
  command, with the look's name and an **Open in Phantra** link carrying
  `?src=discord&server=<guild id>&look=<id>`.
- Limits, checked **before any upload**: 100 MB (Discord says the size up
  front) and 15 s (the bytes are read from Discord's CDN and `ffprobe` on the
  bot's host measures them; a clip that cannot be measured is refused).
- A per-user daily cap (`PHANTRA_BOT_DAILY_CAP`, default 5 per UTC day), in
  memory and in a SQLite file under `PHANTRA_BOT_STATE_DIR`.
- **Free only.** The API is asked for a quote first; anything above 0 credits
  is refused in words ("not free right now") and never run. The run itself is
  sent with `expect_credits: 0`, so the API refuses (409 `price_changed`) a
  look whose price moved between the two calls.
- **One direct message, ever:** a welcome on member join, gated by
  `PHANTRA_BOT_WELCOME_DM` (default on) and marked in the store before it is
  sent, so it is never repeated, even when the person's settings refuse it.
  Commands answer in the channel (a thread) or privately to the interaction
  (ephemeral); the bot never DMs or posts anywhere unasked.

## Installing it on a server (public app)

In the [Discord developer portal](https://discord.com/developers/applications):

1. New Application -> Bot. Copy the token into the bot host's environment as
   `DISCORD_BOT_TOKEN` (never into the repo).
2. **Installation**: User Install off, Guild Install on. Default install
   settings, scopes `bot` and `applications.commands`.
3. **Bot permissions** (the integer is computed by the portal):
   View Channels, Send Messages, Send Messages in Threads, Create Public
   Threads, Attach Files, Embed Links, Read Message History.
4. **Privileged intents**: Server Members Intent on, only if the welcome DM is
   on (`PHANTRA_BOT_WELCOME_DM=1`); the bot sets `intents.members` from that
   flag. Message Content is NOT needed (slash commands carry their own data).
5. The install link has this shape:

       https://discord.com/oauth2/authorize?client_id=<APPLICATION_ID>&scope=bot%20applications.commands&permissions=<PERMISSIONS_INTEGER>

   Anyone with Manage Server on their server can use it; the commands are
   global (synced on `on_ready`, which Discord propagates within an hour).

## Running it

    python -m venv bots/venv && bots/venv/bin/pip install -r bots/requirements.txt
    export DISCORD_BOT_TOKEN=...   PHANTRA_API_BASE=https://api.phantra.ai   PHANTRA_BOT_API_KEY=...
    bots/venv/bin/python -m bots.discord

The host needs `ffprobe` on its PATH. All settings, by name, are listed in
`.env.example` under "the bots"; the bot refuses to start and names the
missing ones.

### How the bot authenticates to the API (read this)

Every `/api` route is gated by the `phantra_session` cookie
(`app/auth.py`, `current_account_id`); the operator key `PHANTRA_MCP_TOKEN`
opens `/mcp`, not `/api`, and the OAuth bearer path (`app/mcp_auth.py`) is
the connector's. So today `PHANTRA_BOT_API_KEY` is a **session cookie value
minted for the bot's own workspace** (`PHANTRA_BOT_API_AUTH=cookie`, the
default), and every clip and look the bot runs is filed in that workspace's
Library (`/api/cut/media` uploads, `/api/effects/run` jobs). A session lasts
30 days (`auth.SESSION_MAX_AGE`), so the value has to be re-minted; a
service-key door on the API (`PHANTRA_BOT_API_AUTH=bearer` sends the key as
`Authorization: Bearer`) is the proper fix and is listed for Mike in
`docs/tasks/task-bots.md`.

## The API calls, in order

| step | call | note |
|---|---|---|
| table | `GET /api/effects` | free; filtered to 0-credit allowlisted rows |
| upload | `POST /api/cut/media` (multipart `file`) | -> `asset:<id>` |
| price | `POST /api/effects/quote` | spends nothing; > 0 -> refused |
| run | `POST /api/effects/run` with `expect_credits: 0` | -> `job_id` |
| wait | `GET /api/jobs/<id>` until `done` | `output` is the clip's URL |
| post | fetch the output, `thread.send(file=...)` | over 25 MB -> the link instead |

## Tests

    venv/bin/python -m pytest bots/discord -q

They run against an API faked over `httpx.MockTransport` and duck-typed
Discord objects (`tests/conftest.py`); `bots/conftest.py` blocks every
socket, so a test can never reach Discord, Reddit or Phantra. `discord.py`
is not installed in the project's venv: the flow (`flow.py`) is tested
without it, and the one test of the wiring (`test_bot.py`) skips with the
reason.

## Not built yet

- The API-side service credential (above).
- Posting outputs larger than the server's upload limit (the thread gets the
  link instead).
- A per-server opt-out of the welcome DM (the flag is per bot host).
