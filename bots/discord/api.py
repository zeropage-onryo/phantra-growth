"""The bot's client of the Phantra API (2026-10-22). HTTP only: it never
imports a provider SDK and never imports `src/` or `app/`.

The five calls a look needs, in the order the bot makes them:

  effects()                 GET  /api/effects          the table (free to read)
  upload_clip(data, name)   POST /api/cut/media        -> asset:<id>
  quote(effect, handle)     POST /api/effects/quote    -> credits (spends nothing)
  run(effect, handle, 0)    POST /api/effects/run      -> job_id, with expect_credits
  job(id) / wait(id)        GET  /api/jobs/<id>        -> output URL when done

`run` is only ever called with `expect_credits=0`: the API refuses (409
price_changed) a run whose price is not the one named, so a look that has
stopped being free cannot be paid for by the bot by accident. `quote`
is asked first anyway and `NotFree` raised on anything above 0, so the
person is told in words before the API is asked to run.

WHO THE BOT IS to the API. Every `/api` route is gated by the
`phantra_session` cookie (app/auth.py `current_account_id`); the operator
key `PHANTRA_MCP_TOKEN` opens `/mcp`, not `/api`. So the service
credential `PHANTRA_BOT_API_KEY` is, today, a session cookie value minted
for the bot's own workspace (auth mode `cookie`, the default), and every
clip and look the bot runs is filed in THAT workspace. Mode `bearer` sends
it as `Authorization: Bearer` instead, for the day the API grows a
service-key door; nothing on the API side reads that header yet.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

import httpx

SESSION_COOKIE = "phantra_session"
FREE_LOOK_IDS = ("film_grade", "noir", "flash_2000s", "crash_zoom", "vertical_ready")
BUNDLE_ID = "make_it_pro"
ALLOWLIST = FREE_LOOK_IDS + (BUNDLE_ID,)


class APIError(RuntimeError):
    """The API said no, in its own words (`code`, `message`)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message = status, code, message


class NotFree(RuntimeError):
    """The look was quoted above 0 credits: the bot runs nothing priced."""

    def __init__(self, effect: str, credits: int):
        super().__init__(f"{effect} costs {credits} credits; the bot runs free looks only")
        self.effect, self.credits = effect, credits


class JobFailed(RuntimeError):
    pass


def _error_of(resp: httpx.Response) -> APIError:
    code, message = "error", resp.text[:200]
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            code = str(err.get("code") or code)
            message = str(err.get("message") or message)
        elif isinstance(err, str):
            message = err
        elif isinstance(body, dict) and body.get("detail"):
            message = str(body["detail"])
    except ValueError:
        pass
    return APIError(resp.status_code, code, message)


class PhantraAPI:
    """One client per bot process. `client` is injectable (tests hand it an
    httpx.Client over a MockTransport); `sleep` too, so `wait` is tested
    without waiting."""

    def __init__(self, base: str, key: str, *, auth: str = "cookie",
                 client: Optional[httpx.Client] = None, timeout: float = 60.0,
                 sleep: Callable[[float], None] = time.sleep):
        self.base = base.rstrip("/")
        self.auth = auth
        self._sleep = sleep
        headers, cookies = {"User-Agent": "phantra-discord-bot/0.1"}, {}
        if auth == "bearer":
            headers["Authorization"] = f"Bearer {key}"
        else:
            cookies[SESSION_COOKIE] = key
        self._client = client or httpx.Client(base_url=self.base, headers=headers,
                                              cookies=cookies, timeout=timeout,
                                              follow_redirects=False)
        if client is not None:
            # a handed-in client still speaks as the bot
            client.headers.update(headers)
            for k, v in cookies.items():
                client.cookies.set(k, v)

    # -- the calls -----------------------------------------------------
    def _json(self, resp: httpx.Response) -> Any:
        if resp.status_code >= 400:
            raise _error_of(resp)
        return resp.json()

    def effects(self) -> list[dict]:
        """The effects table as the gallery reads it. Free to call."""
        body = self._json(self._client.get("/api/effects"))
        return list(body.get("items") or []) if isinstance(body, dict) else []

    def upload_clip(self, data: bytes, filename: str) -> dict:
        """-> {handle: 'asset:<id>', seconds, kind, ...}."""
        resp = self._client.post("/api/cut/media",
                                 files={"file": (filename, data, "video/mp4")})
        return self._json(resp)

    def quote(self, effect: str, handle: str, options: Optional[dict] = None) -> dict:
        body = {"effect": effect, "sources": [handle], "options": options or {}}
        return self._json(self._client.post("/api/effects/quote", json=body))

    def run(self, effect: str, handle: str, expect_credits: int = 0,
            options: Optional[dict] = None) -> dict:
        if expect_credits != 0:
            raise NotFree(effect, expect_credits)
        body = {"effect": effect, "sources": [handle], "options": options or {},
                "expect_credits": 0}
        return self._json(self._client.post("/api/effects/run", json=body))

    def job(self, job_id: int) -> dict:
        return self._json(self._client.get(f"/api/jobs/{int(job_id)}"))

    def wait(self, job_id: int, *, timeout: float = 600.0, interval: float = 2.0) -> dict:
        """Poll until the job ends. Done -> the job; failed or cancelled ->
        JobFailed with the job's own error text; still running at the
        deadline -> JobFailed('timed out')."""
        deadline = time.monotonic() + timeout
        while True:
            job = self.job(job_id)
            status = str(job.get("status") or "")
            if status == "done":
                return job
            if status in ("failed", "cancelled"):
                raise JobFailed(str(job.get("error") or job.get("detail") or status))
            if time.monotonic() >= deadline:
                raise JobFailed("timed out waiting for the look")
            self._sleep(interval)

    def fetch(self, url: str, *, max_bytes: int = 100 * 1024 * 1024) -> bytes:
        """The finished clip's bytes, for posting as a file. Capped."""
        with self._client.stream("GET", url, follow_redirects=True) as resp:
            if resp.status_code >= 400:
                raise APIError(resp.status_code, "fetch_failed", "the output could not be read")
            out = bytearray()
            for chunk in resp.iter_bytes():
                out += chunk
                if len(out) > max_bytes:
                    raise APIError(413, "too_big", "the output is too large to post")
        return bytes(out)

    # -- the look, end to end --------------------------------------------
    def run_free_look(self, effect: str, data: bytes, filename: str, *,
                      options: Optional[dict] = None, timeout: float = 600.0) -> dict:
        """Upload, quote, refuse anything priced, run at 0, wait. Returns
        {handle, job, output} where `output` is the finished clip's URL."""
        up = self.upload_clip(data, filename)
        handle = str(up.get("handle") or "")
        if not handle.startswith("asset:"):
            raise APIError(500, "no_handle", "the upload came back without a handle")
        q = self.quote(effect, handle, options)
        credits = int(q.get("credits") or 0)
        if credits > 0:
            raise NotFree(effect, credits)
        started = self.run(effect, handle, 0, options)
        job = self.wait(int(started["job_id"]), timeout=timeout)
        output = job.get("output") or (job.get("result") or {}).get("output")
        if not output:
            raise JobFailed("the look finished without an output")
        return {"handle": handle, "job": job, "output": str(output),
                "seconds": up.get("seconds")}
