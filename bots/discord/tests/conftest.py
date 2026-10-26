"""Fakes shared by the Discord bot's tests: an API over httpx's
MockTransport (no socket is ever opened) and duck-typed Discord objects."""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx
import pytest

from bots.discord.api import PhantraAPI

TOKEN = "php_bot-token-for-tests"

# what GET /plugin/v1/looks answers: the table's free rows only (the API
# never lists a priced effect here; a priced row in a test is a mistake the
# bot must still refuse to offer)
FREE_ROWS = [
    {"id": "film_grade", "label": "Film Grade", "credits": 0},
    {"id": "noir", "label": "Noir", "credits": 0},
    {"id": "flash_2000s", "label": "2000s Flash", "credits": 0},
    {"id": "crash_zoom", "label": "Crash-Zoom Hook", "credits": 0},
    {"id": "vertical_ready", "label": "Vertical Ready", "credits": 0},
    {"id": "make_it_pro", "label": "Make It Pro", "credits": 0},
]


class FakeStudio:
    """The Phantra plugin door as the bot sees it, scripted. `free` is
    whether /looks/run takes the look (False -> 402 not_free, as the API
    refuses a priced row); `job_statuses` is the sequence /jobs/<id> walks
    through; `calls` is every request, for assertions."""

    def __init__(self, *, rows=None, free: bool = True, job_statuses=None,
                 upload_seconds: float = 6.0,
                 output: str = "https://media.example.test/m/9/renders/out-abc.mp4"):
        self.rows = FREE_ROWS if rows is None else rows
        self.free = free
        self.job_statuses = list(job_statuses or ["queued", "running", "done"])
        self.upload_seconds = upload_seconds
        self.output = output
        self.calls: list[dict[str, Any]] = []
        self.uploads = 0
        self.runs = 0
        self._job_step = 0
        self.output_bytes = b"\x00\x00\x00\x18ftypisom" + b"v" * 64

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body: Optional[dict] = None
        if request.headers.get("content-type", "").startswith("application/json"):
            body = json.loads(request.content or b"{}")
        self.calls.append({"method": request.method, "path": path, "json": body,
                           "host": request.url.host,
                           "auth": request.headers.get("authorization", ""),
                           "content": request.content if request.method == "POST" else b""})
        if request.url.host == "media.example.test":
            # the bucket: public, and it must never be handed the token
            return httpx.Response(200, content=self.output_bytes,
                                  headers={"content-type": "video/mp4"})
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"error": {"code": "unauthorized",
                                                       "message": "Sign in again."}})
        if path == "/plugin/v1/looks" and request.method == "GET":
            return httpx.Response(200, json={"ok": True, "looks": self.rows})
        if path == "/plugin/v1/upload" and request.method == "POST":
            self.uploads += 1
            return httpx.Response(200, json={"ok": True, "asset": f"asset:{100 + self.uploads}",
                                             "kind": "video", "seconds": self.upload_seconds})
        if path == "/plugin/v1/looks/run":
            if not self.free:
                return httpx.Response(402, json={"error": {
                    "code": "not_free",
                    "message": f"{body['look']} is not a free look. Nothing was charged."}})
            self.runs += 1
            self._job_step = 0
            return httpx.Response(200, json={"ok": True, "job_id": 7, "credits": 0})
        if path.startswith("/plugin/v1/jobs/"):
            status = self.job_statuses[min(self._job_step, len(self.job_statuses) - 1)]
            self._job_step += 1
            job = {"id": 7, "status": status, "error": None}
            if status == "done":
                job["output"] = self.output
            if status == "failed":
                job["error"] = "ffmpeg could not read the clip"
            return httpx.Response(200, json={"ok": True, "job": job})
        if path.startswith("/renders/"):
            return httpx.Response(200, content=self.output_bytes)
        return httpx.Response(404, json={"error": {"code": "not_found", "message": path}})


@pytest.fixture
def studio():
    return FakeStudio()


def api_over(studio: FakeStudio, *, token: str = TOKEN) -> PhantraAPI:
    transport = httpx.MockTransport(studio.handler)
    client = httpx.Client(base_url="https://api.example.test", transport=transport)
    media = httpx.Client(transport=transport)
    return PhantraAPI("https://api.example.test", token, client=client, media=media,
                      sleep=lambda s: None)


@pytest.fixture
def api(studio):
    return api_over(studio)


# -- duck-typed Discord ---------------------------------------------------

class FakeUser:
    def __init__(self, id=42, display_name="mike"):
        self.id, self.display_name = id, display_name


class FakeResponse:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []
        self.deferred = False

    def is_done(self):
        return self.deferred or bool(self.sent)

    async def send_message(self, text, **kw):
        self.sent.append((text, kw))

    async def defer(self, **kw):
        self.deferred = True


class FakeThread:
    def __init__(self, name):
        self.name = name
        self.posts: list[dict] = []

    async def send(self, content=None, file=None, **kw):
        self.posts.append({"content": content, "file": file})


class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.thread = None

    async def create_thread(self, name, **kw):
        self.thread = FakeThread(name)
        return self.thread


class FakeFollowup:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []
        self.messages: list[FakeMessage] = []

    async def send(self, text, **kw):
        self.sent.append((text, kw))
        msg = FakeMessage(text)
        self.messages.append(msg)
        return msg


class FakeInteraction:
    def __init__(self, user=None, guild_id=998877):
        self.user = user or FakeUser()
        self.guild_id = guild_id
        self.response = FakeResponse()
        self.followup = FakeFollowup()

    def private_messages(self) -> list[str]:
        return [t for t, kw in self.response.sent + self.followup.sent if kw.get("ephemeral")]


class FakeAttachment:
    def __init__(self, data=b"\x00" * 2048, filename="clip.mp4", size=None,
                 content_type="video/mp4"):
        self.data, self.filename, self.content_type = data, filename, content_type
        self.size = len(data) if size is None else size
        self.reads = 0

    async def read(self):
        self.reads += 1
        return self.data


class FakeMember:
    def __init__(self, id=42):
        self.id = id
        self.dms: list[str] = []
        self.refuse_dms = False

    async def send(self, text):
        if self.refuse_dms:
            raise RuntimeError("Cannot send messages to this user")
        self.dms.append(text)
