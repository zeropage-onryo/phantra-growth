"""Fakes shared by the Discord bot's tests: an API over httpx's
MockTransport (no socket is ever opened) and duck-typed Discord objects."""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx
import pytest

from bots.discord.api import SESSION_COOKIE, PhantraAPI

FREE_ROWS = [
    {"id": "film_grade", "label": "Film Grade", "category": "look", "credits": 0, "takes": "video"},
    {"id": "noir", "label": "Noir", "category": "look", "credits": 0, "takes": "video"},
    {"id": "flash_2000s", "label": "2000s Flash", "category": "look", "credits": 0,
     "takes": "video"},
    {"id": "crash_zoom", "label": "Crash-Zoom Hook", "category": "look", "credits": 0,
     "takes": "video"},
    {"id": "vertical_ready", "label": "Vertical Ready", "category": "look", "credits": 0,
     "takes": "video"},
    {"id": "make_it_pro", "label": "Make It Pro", "category": "look", "credits": 0,
     "takes": "video"},
    {"id": "upscale", "label": "Upscale", "category": "finish", "credits": 48, "takes": "video"},
    {"id": "add-sound", "label": "Add sound", "category": "finish", "credits": None,
     "takes": "video"},
]


class FakeStudio:
    """The Phantra API as the bot sees it: the five routes, scripted.
    `price` is what /effects/quote answers; `job_statuses` is the sequence
    /jobs/<id> walks through; `calls` is every request, for assertions."""

    def __init__(self, *, rows=None, price: int = 0, job_statuses=None,
                 upload_seconds: float = 6.0):
        self.rows = FREE_ROWS if rows is None else rows
        self.price = price
        self.job_statuses = list(job_statuses or ["queued", "running", "done"])
        self.upload_seconds = upload_seconds
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
                           "cookie": request.headers.get("cookie", ""),
                           "auth": request.headers.get("authorization", "")})
        cookie = request.headers.get("cookie", "")
        if f"{SESSION_COOKIE}=bot-session-value" not in cookie and \
                request.headers.get("authorization") != "Bearer bot-session-value":
            return httpx.Response(401, json={"detail": "sign in first"})
        if path == "/api/effects" and request.method == "GET":
            return httpx.Response(200, json={"items": self.rows, "ready": True})
        if path == "/api/cut/media" and request.method == "POST":
            self.uploads += 1
            return httpx.Response(200, json={"handle": f"asset:{100 + self.uploads}",
                                             "kind": "video", "seconds": self.upload_seconds})
        if path == "/api/effects/quote":
            return httpx.Response(200, json={"effect": body["effect"], "credits": self.price,
                                             "charged": True})
        if path == "/api/effects/run":
            if body.get("expect_credits") != self.price:
                return httpx.Response(409, json={"error": {"code": "price_changed",
                                                           "message": f"this costs {self.price}"},
                                                 "credits": self.price})
            self.runs += 1
            self._job_step = 0
            return httpx.Response(200, json={"job_id": 7, "credits": self.price})
        if path.startswith("/api/jobs/"):
            status = self.job_statuses[min(self._job_step, len(self.job_statuses) - 1)]
            self._job_step += 1
            job = {"id": 7, "status": status, "error": None}
            if status == "done":
                job["output"] = "https://media.example.test/renders/out-abc.mp4"
            if status == "failed":
                job["error"] = "ffmpeg could not read the clip"
            return httpx.Response(200, json=job)
        if request.url.host == "media.example.test":
            return httpx.Response(200, content=self.output_bytes,
                                  headers={"content-type": "video/mp4"})
        return httpx.Response(404, json={"error": {"code": "not_found", "message": path}})


@pytest.fixture
def studio():
    return FakeStudio()


def api_over(studio: FakeStudio, *, auth: str = "cookie") -> PhantraAPI:
    client = httpx.Client(base_url="https://api.example.test",
                          transport=httpx.MockTransport(studio.handler))
    return PhantraAPI("https://api.example.test", "bot-session-value", auth=auth,
                      client=client, sleep=lambda s: None)


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
