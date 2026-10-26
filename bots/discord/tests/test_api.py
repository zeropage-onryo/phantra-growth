"""The HTTP client on the plugin door (2026-10-26): speaks as the bot with
its token, uploads, runs (free only, the API's 402), polls, fetches without
handing the token to the media host -- over a MockTransport, never a socket."""
import httpx
import pytest

from bots.discord import api as api_mod
from bots.discord.api import APIError, JobFailed, NotFree, PhantraAPI, pair

from .conftest import TOKEN, FakeStudio, api_over


def test_it_speaks_as_the_bot_with_its_bearer_token(api, studio):
    api.effects()
    assert studio.calls[-1]["path"] == "/plugin/v1/looks"
    assert studio.calls[-1]["auth"] == f"Bearer {TOKEN}"


def test_a_wrong_token_is_the_apis_401_in_words(studio):
    bad = api_over(studio, token="php_not-the-token")
    with pytest.raises(APIError) as e:
        bad.effects()
    assert e.value.status == 401 and e.value.code == "unauthorized"


def test_effects_is_the_free_looks_list(api):
    rows = api.effects()
    assert [r["id"] for r in rows][:2] == ["film_grade", "noir"]


def test_run_free_look_is_upload_run_wait(api, studio):
    out = api.run_free_look("noir", b"clipbytes", "mine.mp4")
    paths = [c["path"] for c in studio.calls]
    assert paths[:2] == ["/plugin/v1/upload", "/plugin/v1/looks/run"]
    assert all(p == "/plugin/v1/jobs/7" for p in paths[2:])
    upload = studio.calls[0]
    assert upload["content"] == b"clipbytes"            # raw bytes, typed by the API
    run = studio.calls[1]
    assert run["json"] == {"look": "noir", "source": "asset:101"}
    assert out["handle"] == "asset:101"
    assert out["output"].endswith("out-abc.mp4")
    assert out["job"]["status"] == "done"


def test_a_look_the_api_will_not_run_free_is_not_free(studio):
    """The API refuses (402 not_free) any look that is not free with 0
    credits; the bot says so and nothing ran."""
    studio.free = False
    api = api_over(studio)
    with pytest.raises(NotFree, match="not a free look"):
        api.run_free_look("noir", b"clipbytes", "mine.mp4")
    assert studio.runs == 0
    assert [c["path"] for c in studio.calls] == ["/plugin/v1/upload", "/plugin/v1/looks/run"]


def test_wait_polls_until_done_and_raises_on_failed(studio):
    studio.job_statuses = ["queued", "running", "running", "done"]
    api = api_over(studio)
    assert api.wait(7)["status"] == "done"
    studio.job_statuses = ["running", "failed"]
    studio._job_step = 0
    with pytest.raises(JobFailed, match="ffmpeg could not read"):
        api.wait(7)


def test_wait_times_out_instead_of_spinning(studio, monkeypatch):
    studio.job_statuses = ["running"]
    api = api_over(studio)
    ticks = iter([0.0, 1.0, 2.0, 700.0])
    monkeypatch.setattr(api_mod.time, "monotonic", lambda: next(ticks))
    with pytest.raises(JobFailed, match="timed out"):
        api.wait(7, timeout=600)


def test_the_output_is_fetched_without_the_token(api, studio):
    """The finished clip lives on the media host: the bot's token is never
    sent there."""
    data = api.fetch("https://media.example.test/m/9/renders/out-abc.mp4")
    assert data == studio.output_bytes
    media_call = studio.calls[-1]
    assert media_call["host"] == "media.example.test" and media_call["auth"] == ""


def test_an_output_path_on_the_api_is_fetched_as_the_bot(api, studio):
    data = api.fetch("/renders/fal/out-abc.mp4")
    assert data == studio.output_bytes
    assert studio.calls[-1]["auth"] == f"Bearer {TOKEN}"


def test_fetch_caps_the_size(api):
    with pytest.raises(APIError) as e:
        api.fetch("https://media.example.test/m/9/renders/out-abc.mp4", max_bytes=8)
    assert e.value.code == "too_big"


def test_pairing_shows_the_code_and_returns_the_token():
    polls = iter([400, 400, 200])
    said = []

    def handler(request):
        if request.url.path == "/plugin/v1/pair":
            import json
            body = json.loads(request.content)
            assert body["client"] == "discord-bot"
            return httpx.Response(200, json={"secret": "php_secret", "code": "KDPX-7QHR",
                                             "link_url": "https://phantra.ai/studio/link",
                                             "expires_in": 600, "interval": 5})
        status = next(polls)
        if status == 200:
            return httpx.Response(200, json={"ok": True, "token": "php_secret"})
        return httpx.Response(400, json={"error": {"code": "authorization_pending",
                                                   "message": "Waiting."}})

    client = httpx.Client(base_url="https://api.example.test",
                          transport=httpx.MockTransport(handler))
    token = pair("https://api.example.test", client=client, sleep=lambda s: None,
                 say=said.append)
    assert token == "php_secret"
    assert any("KDPX-7QHR" in line for line in said)
    assert any("phantra.ai/studio/link" in line for line in said)


def test_pairing_stops_when_the_code_expires():
    def handler(request):
        if request.url.path == "/plugin/v1/pair":
            return httpx.Response(200, json={"secret": "s", "code": "AAAA-BBBB",
                                             "link_url": "x", "expires_in": 600, "interval": 5})
        return httpx.Response(400, json={"error": {"code": "expired_token",
                                                   "message": "The code expired."}})

    client = httpx.Client(base_url="https://api.example.test",
                          transport=httpx.MockTransport(handler))
    with pytest.raises(APIError) as e:
        pair("https://api.example.test", client=client, sleep=lambda s: None,
             say=lambda s: None)
    assert e.value.code == "expired_token"


def test_the_client_never_imports_a_provider_sdk():
    import sys
    for name in ("fal_client", "google.genai", "replicate", "runwayml"):
        assert name not in sys.modules or "bots" not in str(getattr(sys.modules[name], "__file__", ""))
    src = open(api_mod.__file__).read()
    for word in ("fal_client", "import src", "from src", "import app", "from app"):
        assert word not in src


def test_fake_studio_is_a_fixture_not_a_server():
    """Sanity: the transport is a function, nothing listens anywhere."""
    s = FakeStudio()
    r = s.handler(httpx.Request("GET", "https://api.example.test/plugin/v1/looks"))
    assert r.status_code == 401        # no token: the real door's answer


def test_the_constructor_takes_no_cookie_mode():
    """The cookie stopgap is gone: a bot is a plugin token or nothing."""
    import inspect
    assert "auth" not in inspect.signature(PhantraAPI).parameters
