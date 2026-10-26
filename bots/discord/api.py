"""The bot's client of the Phantra API (2026-10-22; door changed 2026-10-26).
HTTP only: it never imports a provider SDK and never imports the studio's
`src/` or `app/`.

WHO THE BOT IS to the API. A plugin token of the `discord-bot` kind, on the
same door the editor panels use (`/plugin/v1`, app/plugin_api.py in the
studio repo). `pair()` gets one: it shows a code, a member of the
workspace the bot should file into approves it at phantra.ai/studio/link,
and the token comes back. Set it as `PHANTRA_BOT_API_KEY`. It is revocable
in the studio (Settings -> Connections) and dies after 90 idle days, which
a running bot never reaches. A bot token reaches ONLY the routes below:
every panel tool is 403 `not_for_bots`, so it can never quote or spend.

The calls a look needs, in the order the bot makes them:

  effects()               GET  /plugin/v1/looks       the free looks switched on
  upload_clip(data, name) POST /plugin/v1/upload      raw bytes -> asset:<id>
  run(look, handle)       POST /plugin/v1/looks/run   -> job_id (402 not_free if priced)
  job(id) / wait(id)      GET  /plugin/v1/jobs/<id>   -> the output when done

The API refuses any look that is not free with 0 credits (402 `not_free`),
which arrives here as `NotFree`: the bot cannot pay for anything, by
design on the server, not by promise here.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

import httpx

FREE_LOOK_IDS = ("film_grade", "noir", "flash_2000s", "crash_zoom", "vertical_ready")
BUNDLE_ID = "make_it_pro"
ALLOWLIST = FREE_LOOK_IDS + (BUNDLE_ID,)
CLIENT_KIND = "discord-bot"
USER_AGENT = "phantra-discord-bot/0.2"


class APIError(RuntimeError):
    """The API said no, in its own words (`code`, `message`)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message = status, code, message


class NotFree(RuntimeError):
    """The API refused the look because it is not free: the bot runs free
    looks only."""

    def __init__(self, effect: str, message: str = ""):
        super().__init__(message or f"{effect} is not a free look")
        self.effect = effect


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
    httpx.Client over a MockTransport), and so are `media` (the plain client
    that fetches a finished clip from the bucket, which must never see the
    token) and `sleep`, so `wait` is tested without waiting."""

    def __init__(self, base: str, token: str, *,
                 client: Optional[httpx.Client] = None,
                 media: Optional[httpx.Client] = None,
                 timeout: float = 120.0,
                 sleep: Callable[[float], None] = time.sleep):
        self.base = base.rstrip("/")
        self._origin = _origin(self.base)
        self._sleep = sleep
        headers = {"User-Agent": USER_AGENT, "Authorization": f"Bearer {token}"}
        self._client = client or httpx.Client(base_url=self.base, timeout=timeout,
                                              follow_redirects=False)
        self._client.headers.update(headers)
        # no Authorization here, ever: the output lives on the media host
        self._media = media or httpx.Client(timeout=timeout, follow_redirects=True,
                                            headers={"User-Agent": USER_AGENT})

    def _json(self, resp: httpx.Response) -> Any:
        if resp.status_code >= 400:
            raise _error_of(resp)
        return resp.json()

    # -- the calls -----------------------------------------------------
    def effects(self) -> list[dict]:
        """The free looks the API offers: [{id, label, credits: 0}]."""
        body = self._json(self._client.get("/plugin/v1/looks"))
        return list(body.get("looks") or []) if isinstance(body, dict) else []

    def upload_clip(self, data: bytes, filename: str = "") -> dict:
        """The clip's raw bytes -> {handle: 'asset:<id>', seconds, kind}.
        The API types a file by its bytes, never its name."""
        resp = self._client.post("/plugin/v1/upload", content=data,
                                 headers={"Content-Type": "application/octet-stream"})
        body = self._json(resp)
        return {**body, "handle": body.get("asset") or body.get("handle")}

    def run(self, look: str, handle: str) -> dict:
        """-> {job_id}. A look that is not free is the API's 402 -> NotFree."""
        resp = self._client.post("/plugin/v1/looks/run",
                                 json={"look": look, "source": handle})
        if resp.status_code == 402:
            raise NotFree(look, _error_of(resp).message)
        return self._json(resp)

    def job(self, job_id: int) -> dict:
        body = self._json(self._client.get(f"/plugin/v1/jobs/{int(job_id)}"))
        return body.get("job") if isinstance(body, dict) and "job" in body else body

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
        """The finished clip's bytes, for posting as a file. Capped. A path
        on the API (no bucket) is read with the bot's own client; anything
        else is read WITHOUT the token, so it never reaches the media host."""
        if url.startswith("/"):
            stream = self._client.stream("GET", url)
        elif _origin(url) == self._origin:
            stream = self._client.stream("GET", url)
        else:
            stream = self._media.stream("GET", url)
        with stream as resp:
            if resp.status_code >= 400:
                raise APIError(resp.status_code, "fetch_failed", "the output could not be read")
            out = bytearray()
            for chunk in resp.iter_bytes():
                out += chunk
                if len(out) > max_bytes:
                    raise APIError(413, "too_big", "the output is too large to post")
        return bytes(out)

    # -- the look, end to end --------------------------------------------
    def run_free_look(self, look: str, data: bytes, filename: str, *,
                      timeout: float = 600.0) -> dict:
        """Upload, run (free only, the API's rule), wait. Returns
        {handle, job, output, seconds} where `output` is the finished clip."""
        up = self.upload_clip(data, filename)
        handle = str(up.get("handle") or "")
        if not handle.startswith("asset:"):
            raise APIError(500, "no_handle", "the upload came back without a handle")
        started = self.run(look, handle)
        job = self.wait(int(started["job_id"]), timeout=timeout)
        output = job.get("output") or (job.get("result") or {}).get("output")
        if not output:
            raise JobFailed("the look finished without an output")
        return {"handle": handle, "job": job, "output": str(output),
                "seconds": up.get("seconds")}


def _origin(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return (parts.scheme.lower(), parts.netloc.lower())


# -- getting a token ---------------------------------------------------------

def pair(base: str, *, device: str = "Phantra Discord bot",
         client: Optional[httpx.Client] = None,
         sleep: Callable[[float], None] = time.sleep,
         say: Callable[[str], None] = print) -> str:
    """Sign the bot in, once, from a terminal: show the code, wait while a
    person approves it at the studio's link page, return the token. Raises
    APIError if the code expires or the API says no."""
    http = client or httpx.Client(base_url=base.rstrip("/"), timeout=30.0,
                                  headers={"User-Agent": USER_AGENT})
    started = http.post("/plugin/v1/pair", json={"client": CLIENT_KIND, "device": device})
    if started.status_code >= 400:
        raise _error_of(started)
    s = started.json()
    say(f"Open {s['link_url']} signed in to the workspace the bot should use,")
    say(f"and enter this code: {s['code']}   (it expires in {s['expires_in'] // 60} minutes)")
    deadline = time.monotonic() + float(s["expires_in"])
    while time.monotonic() < deadline:
        sleep(float(s.get("interval") or 5))
        polled = http.post("/plugin/v1/pair/token", json={"secret": s["secret"]})
        if polled.status_code == 200:
            return str(polled.json()["token"])
        err = _error_of(polled)
        if err.code != "authorization_pending":
            raise err
    raise APIError(400, "expired_token", "The code expired. Run pair again.")
