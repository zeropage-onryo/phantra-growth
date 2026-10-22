"""The HTTP client: speaks as the bot, uploads, quotes, runs at 0 only,
polls, fetches -- over a MockTransport, never a socket."""
import httpx
import pytest

from bots.discord import api as api_mod
from bots.discord.api import APIError, JobFailed, NotFree, PhantraAPI

from .conftest import FakeStudio, api_over


def test_it_speaks_as_the_bot_with_the_session_cookie(api, studio):
    api.effects()
    assert studio.calls[-1]["cookie"] == "phantra_session=bot-session-value"
    assert studio.calls[-1]["auth"] == ""


def test_bearer_mode_sends_the_key_as_a_bearer_instead(studio):
    api = api_over(studio, auth="bearer")
    api.effects()
    assert studio.calls[-1]["auth"] == "Bearer bot-session-value"
    assert "phantra_session" not in studio.calls[-1]["cookie"]


def test_a_wrong_credential_is_the_apis_401_in_words(studio):
    client = httpx.Client(base_url="https://api.example.test",
                          transport=httpx.MockTransport(studio.handler))
    bad = PhantraAPI("https://api.example.test", "not-the-key", client=client)
    with pytest.raises(APIError) as e:
        bad.effects()
    assert e.value.status == 401


def test_effects_is_the_tables_items(api):
    rows = api.effects()
    assert [r["id"] for r in rows][:2] == ["film_grade", "noir"]


def test_run_free_look_is_upload_quote_run_at_zero_wait(api, studio):
    out = api.run_free_look("noir", b"clipbytes", "mine.mp4")
    paths = [c["path"] for c in studio.calls]
    assert paths[:3] == ["/api/cut/media", "/api/effects/quote", "/api/effects/run"]
    assert all(p == "/api/jobs/7" for p in paths[3:])
    run = next(c for c in studio.calls if c["path"] == "/api/effects/run")
    assert run["json"] == {"effect": "noir", "sources": ["asset:101"], "options": {},
                           "expect_credits": 0}
    assert out["handle"] == "asset:101"
    assert out["output"].endswith("out-abc.mp4")
    assert out["job"]["status"] == "done"


def test_a_priced_quote_stops_before_the_run(studio):
    studio.price = 48
    api = api_over(studio)
    with pytest.raises(NotFree) as e:
        api.run_free_look("noir", b"clipbytes", "mine.mp4")
    assert e.value.credits == 48
    assert studio.runs == 0
    assert [c["path"] for c in studio.calls] == ["/api/cut/media", "/api/effects/quote"]


def test_run_itself_refuses_any_price_above_zero(api, studio):
    with pytest.raises(NotFree):
        api.run("noir", "asset:1", expect_credits=10)
    assert studio.runs == 0


def test_the_apis_price_changed_409_is_an_api_error(studio):
    """If the table moved between quote and run, the API refuses at 409;
    the bot reports it and nothing ran."""
    api = api_over(studio)
    studio.price = 0
    api.quote("noir", "asset:1")
    studio.price = 12                      # moved under the bot's feet
    with pytest.raises(APIError) as e:
        api.run("noir", "asset:1", 0)
    assert e.value.code == "price_changed"
    assert studio.runs == 0


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


def test_fetch_reads_the_output_and_caps_its_size(api, studio):
    data = api.fetch("https://media.example.test/renders/out-abc.mp4")
    assert data == studio.output_bytes
    with pytest.raises(APIError) as e:
        api.fetch("https://media.example.test/renders/out-abc.mp4", max_bytes=8)
    assert e.value.code == "too_big"


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
    r = s.handler(httpx.Request("GET", "https://api.example.test/api/effects"))
    assert r.status_code == 401        # no cookie: the real gate's answer
