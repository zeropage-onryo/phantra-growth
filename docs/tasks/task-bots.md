# Task — Bots: the Discord bot and the read-only Reddit listener

**From:** group 8 of `docs/tasks/task-overnight-2026-10-22.md` (Mike, 2026-10-22, 00:25 ET:
the Discord bot is a public, installable app; the Reddit listener is read-only; no bot ever
DMs or comments unasked). **Branch:** `claude/overnight-bots`. **Code:** `bots/`.

## As built (2026-10-22)

Everything lives under `bots/`, a package that imports nothing from `src/` or `app/`: a bot
is a client of the API, as the plugins are, and runs on a host of its own with its own venv
(`bots/requirements.txt`: discord.py 2.5.2, praw 7.8.1, httpx 0.28.1, pinned, NOT installed
into the project's venv). `bots/conftest.py` copies `tests/conftest.py`'s socket guard, so a
bot test can never reach Discord, Reddit or the API, and clears the bots' env names.
`venv/bin/python -m pytest bots -q`: 111 passed, 1 skipped (the discord.py wiring test, with
the reason). `bots/common/store.py` is one SQLite file (daily counters + named sets) under
`PHANTRA_BOT_STATE_DIR` (default `bots/state/`, gitignored).

### The Discord bot (`bots/discord/`, README inside)

- `/look clip:<attachment> look:<pick>` and `/makeitpro clip:<attachment>`. The dropdown is
  an autocomplete over the FREE looks: `GET /api/effects` read at runtime (re-read every 10
  minutes), kept only where the row's `credits` is 0 (or `free: true`) AND the id is on the
  allowlist `film_grade, noir, flash_2000s, crash_zoom, vertical_ready, make_it_pro`
  (`api.ALLOWLIST`). A priced row on the list is not offered; a free row off the list is not
  offered; when the table cannot be read, the allowlist itself is offered and the quote gates
  the run. The bundle never appears in `/look`'s dropdown.
- The flow (`flow.py`, written against duck-typed Discord objects so it is tested without the
  library): cap -> the look is offered -> it is a video -> size (Discord says it before any
  download) -> defer -> read the bytes from Discord's CDN -> `ffprobe` on the bot host
  (`clipcheck.py`; unmeasurable = refused) -> upload `POST /api/cut/media` -> quote
  `POST /api/effects/quote` (above 0 credits = "not free right now", nothing runs) ->
  `POST /api/effects/run` with `expect_credits: 0` (the API's own 409 `price_changed` is the
  second wall) -> poll `GET /api/jobs/<id>` -> fetch the output -> a thread under the bot's
  reply to the command, the clip posted AS A FILE (over 25 MB: the link instead) with the
  look's name and `Open in Phantra: https://phantra.ai/studio?src=discord&server=<guild id>&look=<id>`.
  Limits 100 MB / 15 s, in words. Per-user daily cap (`PHANTRA_BOT_DAILY_CAP`, default 5, UTC
  day) in memory and in the store; a failed run never counts.
- The ONE direct message: a welcome on `on_member_join`, gated by `PHANTRA_BOT_WELCOME_DM`
  (default on), marked in the store BEFORE sending so it is never repeated, even when the
  person's settings refuse it. A test counts `member.send(` in the flow: exactly one, and no
  `user.send` / `create_dm` anywhere. Commands answer ephemerally or in the thread.
- Public app: global commands synced on `on_ready`, no guild id anywhere, `intents.members`
  only when the welcome is on, Message Content not requested. README has the install URL
  shape (`scope=bot%20applications.commands`), the permissions and the intents.
- Credentials by name only: `DISCORD_BOT_TOKEN`, `PHANTRA_API_BASE`, `PHANTRA_BOT_API_KEY`
  (+ `PHANTRA_BOT_API_AUTH`, `PHANTRA_BOT_STATE_DIR`, `PHANTRA_BOT_DAILY_CAP`,
  `PHANTRA_BOT_WELCOME_DM`, `PHANTRA_OPEN_URL`), empty in `.env.example`; a test asserts the
  names are there with empty values and no token-shaped string is in `bots/`. The bot refuses
  to start and names what is missing.
- **How the bot is a caller of `/api` (the open point).** Every `/api` route is gated by the
  `phantra_session` cookie (`app/auth.py current_account_id`); `PHANTRA_MCP_TOKEN` opens
  `/mcp`, not `/api`; the OAuth bearer path is the connector's. So today `PHANTRA_BOT_API_KEY`
  is a session cookie value minted for the bot's own workspace (auth mode `cookie`, default),
  it expires with the session (30 days), and every upload and look is filed in that
  workspace's Library. Mode `bearer` sends it as `Authorization: Bearer` for the day the API
  grows a service-key door; nothing reads it yet. See MIKE below.

### The Reddit listener (`bots/reddit_listener/`, README inside)

- `python -m bots.reddit_listener [--once] [--interval 300] [--limit 50]`. Six subreddits
  (`REDDIT_SUBREDDITS` replaces), the brief's phrases plus near neighbours
  (`config.DEFAULT_PHRASES`; `REDDIT_INTENT_PHRASES`, `|`-separated, adds), matched case- and
  whitespace-insensitively over title + body. Every post seen is marked in the store (matched
  or not), so nothing is read or alerted twice, across restarts.
- Alerts: `WebhookAlert` (one Discord channel webhook, `REDDIT_ALERT_WEBHOOK_URL`, mentions
  off), `EmailAlert` (`REDDIT_ALERT_SMTP_*`, `REDDIT_ALERT_FROM/TO`, STARTTLS), `StdoutAlert`
  when neither is set. A failing alerter is a stderr line.
- **Read-only, proven three ways.** `facade.ReadOnlyReddit` exposes `new_posts()` only, raises
  by name on every write method (`WRITE_METHODS`), passes nothing through, is sealed, and
  returns plain dicts (only attributes are read on a Submission; a test hands it objects whose
  every method raises). `test_read_only.py` runs a full cycle over a `MagicMock` client and
  asserts the only calls were `subreddit(<name>)` and `.new(limit=...)`, no write name was
  called on the client or any subreddit mock, and the package source names no write call.
  `build_client` makes the PRAW client with id, secret and user agent only and sets
  `read_only = True`.
- Credentials by name: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` (already in `.env.example`
  for the reference-image lane; the same "script" app serves), `REDDIT_USER_AGENT`, plus the
  alert names above, all empty in `.env.example`. Fixtures are hand-written in PRAW's shape,
  never recorded.

### Not verified

- Neither bot was run against Discord, Reddit or the live API (no developer apps exist yet;
  the stream spends nothing). The API contract the bot codes to was read from `app/api.py`
  (`/api/effects`, `/api/effects/quote`, `/api/effects/run` + `expect_credits`, `/api/jobs/<id>`)
  and `app/cut_routes.py` (`POST /api/cut/media` -> `asset:<id>`), and the fake API in the
  tests answers in those shapes, including the real gate's 401 without the cookie.
- The free looks' rows (`film_grade` ... `make_it_pro`) are the free-looks stream's
  (`claude/overnight-looks`); the bot reads whatever `GET /api/effects` says and refuses
  anything priced, so it is correct before and after that merge. If that stream names a row's
  freeness differently from `credits: 0` / `free: true`, `looks._is_free` is the one place to
  teach it.
- Discord's per-server upload limit for a bot's file (10 MB on an unboosted server as of
  2025) is below the bot's 25 MB post ceiling; above the server's limit the `thread.send`
  fails and the thread gets the link, which the flow handles but no test exercises against
  the real library.

## MIKE (later)

- [ ] Create the Discord application (developer portal): Bot, public Guild Install with
  scopes `bot` + `applications.commands`, the permissions in `bots/discord/README.md`, Server
  Members Intent if the welcome DM stays on. Put `DISCORD_BOT_TOKEN` in the bot host's env.
- [ ] Decide the bot's API identity: (a) make a `phantra-bot` workspace, mint a
  `phantra_session` cookie value for a member of it (itsdangerous with `SESSION_SECRET`, as
  `app/auth.py` does) and set it as `PHANTRA_BOT_API_KEY` (expires in 30 days), or (b) ask for
  a small API change: a service-key door on `/api` for `Authorization: Bearer
  <PHANTRA_BOT_API_KEY>` bound to one workspace (then `PHANTRA_BOT_API_AUTH=bearer`). (b) is the
  right one; it is a security surface and was not built overnight.
- [ ] Create the Reddit "script" app (reddit.com/prefs/apps); set `REDDIT_CLIENT_ID`,
  `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`; pick where alerts go (a Discord channel webhook
  URL into `REDDIT_ALERT_WEBHOOK_URL`, or the SMTP names) and set them in env yourself.
- [ ] Pick the hosts: both are long-running processes outside the API (the Fly image runs
  one cron line and nothing else by your choice; the Mac runs no agents). A small Fly machine
  per bot, or one machine running both, is the obvious shape.
- [ ] Say whether the welcome DM stays on by default (`PHANTRA_BOT_WELCOME_DM`), and the
  daily cap (`PHANTRA_BOT_DAILY_CAP`, 5).
