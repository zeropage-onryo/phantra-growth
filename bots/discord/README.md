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

### How the bot signs in to Phantra (2026-10-26)

The bot is a **plugin token** of the `discord-bot` kind, on the same door the
editor panels use (`/plugin/v1`, `app/plugin_api.py` in the studio repo,
PR #503). Get one once, from any machine:

    PHANTRA_API_BASE=https://api.phantra.ai venv/bin/python -m bots.discord pair

It prints a code. Open phantra.ai/studio/link **signed in to the workspace
the bot should file its clips into**, enter the code, and the token is
printed. Set it as `PHANTRA_BOT_API_KEY` (on Fly: `fly secrets set`).

- It never expires while the bot runs (90 idle days), and it is revoked in
  the studio under Settings -> Connections ("Discord bot").
- A bot token reaches only `/me`, `/upload`, `/looks`, `/looks/run` and
  `/jobs/<id>`. Every panel tool is 403 `not_for_bots`, so the bot can never
  quote, approve or spend, by the server's rule rather than by promise here.
- `/looks/run` refuses (402 `not_free`) any look that is not free with 0
  credits; the bot tells the person, in the channel, and nothing is charged.
- Every clip and look is filed in the approving workspace's Library.

## The API calls, in order

| step | call | note |
|---|---|---|
| looks | `GET /plugin/v1/looks` | the free looks switched on; filtered to the allowlist |
| upload | `POST /plugin/v1/upload` (the clip's raw bytes) | -> `asset:<id>` |
| run | `POST /plugin/v1/looks/run {look, source}` | -> `job_id`; 402 `not_free` if priced |
| wait | `GET /plugin/v1/jobs/<id>` until `done` | `output` is the clip's address |
| post | fetch the output (without the token if it is on the media host), `thread.send(file=...)` | over the server's limit -> the link instead |

## Tests

    venv/bin/python -m pytest bots/discord -q

They run against an API faked over `httpx.MockTransport` and duck-typed
Discord objects (`tests/conftest.py`); `bots/conftest.py` blocks every
socket, so a test can never reach Discord, Reddit or Phantra. The flow
(`flow.py`) is tested without `discord.py`; the one test of the wiring
(`test_bot.py`) needs it installed (it is in `bots/requirements.txt`) and
skips with the reason otherwise. CI installs it, so it always runs there:
while this lived in the studio repo it always skipped, and it was hiding a
startup crash (fixed 2026-10-22, see the note at the top of `bot.py`).

## Not built yet

- The API-side service credential (above).
- Posting outputs larger than the server's upload limit (the thread gets the
  link instead).
- A per-server opt-out of the welcome DM (the flag is per bot host).
