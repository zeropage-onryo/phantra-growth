"""The commands end to end against fakes: the thread, the file, the
link, every refusal, and the single welcome."""
import asyncio

import pytest

from bots.common.store import LocalStore
from bots.discord import flow
from bots.discord.config import Settings
from bots.discord.flow import Services, run_look_command, welcome_member

from .conftest import FakeAttachment, FakeInteraction, FakeMember, api_over


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


async def _inline(fn, *args):
    return fn(*args)


def services_for(studio, *, seconds=6.0, cap=5, welcome=True, store=None, clock=None):
    settings = Settings.from_env({"DISCORD_BOT_TOKEN": "t", "PHANTRA_BOT_API_KEY": "k",
                                  "PHANTRA_BOT_DAILY_CAP": str(cap),
                                  "PHANTRA_BOT_WELCOME_DM": "1" if welcome else "0"})
    probe_calls = []

    def probe(data, suffix):
        probe_calls.append((len(data), suffix))
        return seconds

    svc = Services(settings, api_over(studio), store if store is not None else LocalStore(),
                   probe=probe, make_file=lambda data, name: ("FILE", name, len(data)),
                   to_thread=_inline, clock=clock or (lambda: 0.0))
    svc.probe_calls = probe_calls
    return svc


def test_look_posts_the_clip_in_a_thread_with_the_open_link(studio):
    svc = services_for(studio)
    ix, clip = FakeInteraction(guild_id=555), FakeAttachment(filename="party.mov")
    out = run(run_look_command(ix, clip, "noir", svc))
    assert out["ok"] and out["look"] == "noir" and out["posted_file"]
    assert ix.response.deferred and clip.reads == 1
    anchor = ix.followup.messages[0]
    assert "Noir" in anchor.text and "4 free looks left" in anchor.text
    assert anchor.thread.name == "Noir · mike"
    post = anchor.thread.posts[0]
    assert post["file"] == ("FILE", "party-noir.mp4", len(studio.output_bytes))
    assert "Open in Phantra: https://phantra.ai/studio?src=discord&server=555&look=noir" \
        in post["content"]
    assert studio.runs == 1 and studio.uploads == 1
    assert svc.probe_calls == [(2048, ".mov")]
    assert ix.private_messages() == []


def test_makeitpro_is_the_bundle_through_the_same_door(studio):
    svc = services_for(studio)
    ix = FakeInteraction()
    out = run(run_look_command(ix, FakeAttachment(), "make_it_pro", svc))
    assert out["ok"] and out["look"] == "make_it_pro"
    run_call = next(c for c in studio.calls if c["path"] == "/api/effects/run")
    assert run_call["json"]["effect"] == "make_it_pro"
    assert run_call["json"]["expect_credits"] == 0


def test_a_look_the_api_prices_is_refused_in_words_and_never_run(studio):
    studio.price = 24
    svc = services_for(studio)
    svc.offered()                       # the table was read while it was free...
    ix = FakeInteraction()
    out = run(run_look_command(ix, FakeAttachment(), "noir", svc))
    assert out == {"ok": False, "reason": "not_free", "credits": 24}
    assert studio.runs == 0
    assert "not free right now (24 credits)" in ix.private_messages()[0]
    assert all(m.thread is None for m in ix.followup.messages)   # no anchor, no thread


def test_a_look_not_on_the_free_list_is_not_offered(studio):
    svc = services_for(studio)
    ix = FakeInteraction()
    out = run(run_look_command(ix, FakeAttachment(), "upscale", svc))
    assert out["reason"] == "not_offered" and studio.uploads == 0
    assert "not on the free list" in ix.private_messages()[0]
    assert "src=discord" in ix.private_messages()[0]


def test_too_big_is_refused_before_any_download_or_upload(studio):
    svc = services_for(studio)
    ix, clip = FakeInteraction(), FakeAttachment(size=100 * 1024 * 1024 + 1)
    out = run(run_look_command(ix, clip, "noir", svc))
    assert out["reason"] == "too_big" and clip.reads == 0 and studio.uploads == 0
    assert "100 MB" in ix.private_messages()[0]


def test_too_long_is_refused_after_the_probe_and_before_any_upload(studio):
    svc = services_for(studio, seconds=15.5)
    ix, clip = FakeInteraction(), FakeAttachment()
    out = run(run_look_command(ix, clip, "noir", svc))
    assert out["reason"] == "too_long" and clip.reads == 1 and studio.uploads == 0
    assert "15s" in ix.private_messages()[0]


def test_a_length_that_cannot_be_measured_is_refused_not_passed(studio):
    svc = services_for(studio, seconds=None)
    ix = FakeInteraction()
    out = run(run_look_command(ix, FakeAttachment(), "noir", svc))
    assert out["reason"] == "unmeasured" and studio.uploads == 0


def test_not_a_video_is_refused(studio):
    svc = services_for(studio)
    ix = FakeInteraction()
    out = run(run_look_command(ix, FakeAttachment(filename="photo.png", content_type="image/png"),
                               "noir", svc))
    assert out["reason"] == "not_video" and studio.uploads == 0


def test_the_daily_cap_holds_per_user(studio, tmp_path):
    store = LocalStore(tmp_path / "s.sqlite")
    svc = services_for(studio, cap=2, store=store)
    for _ in range(2):
        assert run(run_look_command(FakeInteraction(), FakeAttachment(), "noir", svc))["ok"]
    ix = FakeInteraction()
    out = run(run_look_command(ix, FakeAttachment(), "noir", svc))
    assert out["reason"] == "daily_cap" and studio.runs == 2
    assert "today's 2 free looks" in ix.private_messages()[0]
    other = FakeInteraction(user=type("U", (), {"id": 7, "display_name": "sam"})())
    assert run(run_look_command(other, FakeAttachment(), "noir", svc))["ok"]
    # a failed run never counts
    assert store.daily_count("42") == 2


def test_a_failed_job_is_said_plainly_with_nothing_charged(studio):
    studio.job_statuses = ["running", "failed"]
    svc = services_for(studio)
    ix = FakeInteraction()
    out = run(run_look_command(ix, FakeAttachment(), "film_grade", svc))
    assert out["reason"] == "failed"
    msg = ix.private_messages()[0]
    assert "ffmpeg could not read the clip" in msg and "Nothing was charged" in msg
    assert all(m.thread is None for m in ix.followup.messages)
    assert svc.cap.used(42, "any") == 0


def test_an_output_too_large_to_post_becomes_a_link_in_the_thread(studio):
    studio.output_bytes = b"v" * (flow.POST_MAX_BYTES + 1)
    svc = services_for(studio)
    ix = FakeInteraction()
    out = run(run_look_command(ix, FakeAttachment(), "noir", svc))
    assert out["ok"] and not out["posted_file"]
    post = ix.followup.messages[0].thread.posts[0]
    assert post["file"] is None and out["output"] in post["content"]


def test_the_offer_falls_back_to_the_allowlist_when_the_api_is_down(studio):
    svc = services_for(studio)
    svc.api.effects = lambda: (_ for _ in ()).throw(RuntimeError("down"))
    rows = svc.offered()
    assert [r["id"] for r in rows] == list(flow.LOOK_LABELS)
    assert svc.looks_from_fallback


def test_the_offer_is_re_read_after_its_ttl(studio):
    now = [0.0]
    svc = services_for(studio, clock=lambda: now[0])
    svc.offered()
    reads = sum(1 for c in studio.calls if c["path"] == "/api/effects")
    svc.offered()
    assert sum(1 for c in studio.calls if c["path"] == "/api/effects") == reads
    now[0] = flow.LOOKS_TTL + 1
    svc.offered()
    assert sum(1 for c in studio.calls if c["path"] == "/api/effects") == reads + 1


def test_the_welcome_is_sent_once_and_only_once(studio, tmp_path):
    store = LocalStore(tmp_path / "s.sqlite")
    svc = services_for(studio, store=store)
    m = FakeMember(id=9)
    assert run(welcome_member(m, svc)) is True
    assert m.dms == [flow.WELCOME_TEXT]
    assert run(welcome_member(m, svc)) is False
    assert m.dms == [flow.WELCOME_TEXT]
    # a restart does not forget
    again = services_for(studio, store=LocalStore(tmp_path / "s.sqlite"))
    assert run(welcome_member(m, again)) is False and len(m.dms) == 1


def test_the_welcome_is_off_by_flag_and_never_retried_when_refused(studio):
    off = services_for(studio, welcome=False)
    m = FakeMember()
    assert run(welcome_member(m, off)) is False and m.dms == []
    on = services_for(studio)
    m.refuse_dms = True
    assert run(welcome_member(m, on)) is False
    m.refuse_dms = False
    assert run(welcome_member(m, on)) is False and m.dms == []


def test_no_other_direct_message_exists_in_the_flow():
    """`member.send` in welcome_member is the only DM; a command answers
    the interaction (ephemeral or the thread), never the person's inbox."""
    import inspect
    src = inspect.getsource(flow)
    assert src.count("member.send(") == 1
    assert "user.send(" not in src and "create_dm(" not in src and "dm_channel" not in src


@pytest.mark.parametrize("name", ["look", "makeitpro"])
def test_both_commands_share_one_flow(name):
    from bots.discord import bot
    src = open(bot.__file__).read()
    assert f'name="{name}"' in src
    assert src.count("flow.run_look_command(") == 2
