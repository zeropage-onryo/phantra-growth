"""The rules: free and allowlisted only, the limits, the cap, the link."""
from bots.common.store import LocalStore
from bots.discord.api import ALLOWLIST
from bots.discord.config import MAX_BYTES, MAX_SECONDS, Settings
from bots.discord.looks import DailyCap, check_clip, fallback_looks, free_looks, open_link, single_looks

from .conftest import FREE_ROWS


def test_free_looks_are_the_zero_priced_allowlisted_rows_in_order():
    rows = free_looks(FREE_ROWS)
    assert [r["id"] for r in rows] == list(ALLOWLIST)
    assert rows[-1]["bundle"] is True and rows[0]["bundle"] is False


def test_a_priced_row_on_the_list_is_not_offered():
    rows = [dict(r, credits=(30 if r["id"] == "noir" else r["credits"])) for r in FREE_ROWS]
    assert "noir" not in [r["id"] for r in free_looks(rows)]


def test_a_free_row_off_the_list_is_not_offered():
    rows = FREE_ROWS + [{"id": "remove-background", "label": "Cut out", "credits": 0}]
    assert "remove-background" not in [r["id"] for r in free_looks(rows)]


def test_a_price_that_depends_on_the_clip_is_not_free():
    assert free_looks([{"id": "noir", "label": "Noir", "credits": None}]) == []


def test_a_free_flag_counts_too():
    assert [r["id"] for r in free_looks([{"id": "noir", "label": "Noir", "free": True}])] == ["noir"]


def test_the_fallback_is_the_allowlist_itself():
    assert [r["id"] for r in fallback_looks()] == list(ALLOWLIST)


def test_the_dropdown_never_shows_the_bundle():
    assert "make_it_pro" not in [r["id"] for r in single_looks(fallback_looks())]
    assert len(single_looks(fallback_looks())) == 5


def test_clip_limits_are_15s_and_100mb_in_words():
    assert check_clip(1000, 14.9) is None
    assert check_clip(MAX_BYTES, MAX_SECONDS) is None
    assert "100 MB" in check_clip(MAX_BYTES + 1, 3.0)
    assert "15s" in check_clip(1000, 15.4)
    assert "measure" in check_clip(1000, None)
    assert "size" in check_clip(None, 3.0)


def test_daily_cap_counts_per_user_per_day_and_survives_a_restart(tmp_path):
    store = LocalStore(tmp_path / "s.sqlite")
    cap = DailyCap(2, store)
    assert cap.allows(1, "2026-10-22") and cap.left(1, "2026-10-22") == 2
    cap.count(1, "2026-10-22")
    cap.count(1, "2026-10-22")
    assert not cap.allows(1, "2026-10-22")
    assert cap.allows(2, "2026-10-22")              # another person
    assert cap.allows(1, "2026-10-23")              # tomorrow
    again = DailyCap(2, LocalStore(tmp_path / "s.sqlite"))   # a restart
    assert again.used(1, "2026-10-22") == 2 and not again.allows(1, "2026-10-22")


def test_daily_cap_without_a_store_is_memory_only():
    cap = DailyCap(1)
    assert cap.allows("u", "d")
    cap.count("u", "d")
    assert not cap.allows("u", "d")


def test_open_link_carries_the_server_tracking_parameters():
    link = open_link("https://phantra.ai/studio", 998877, "noir")
    assert link == "https://phantra.ai/studio?src=discord&server=998877&look=noir"
    assert open_link("https://phantra.ai/studio/", None) == \
        "https://phantra.ai/studio?src=discord&server=dm"


def test_settings_read_names_from_the_environment_only():
    s = Settings.from_env({"DISCORD_BOT_TOKEN": "t", "PHANTRA_BOT_API_KEY": "k",
                           "PHANTRA_BOT_DAILY_CAP": "3", "PHANTRA_BOT_WELCOME_DM": "0"})
    assert s.token == "t" and s.api_key == "k" and s.daily_cap == 3 and s.welcome_dm is False
    assert s.api_base == "https://api.phantra.ai" and s.open_url == "https://phantra.ai/studio"
    assert s.missing() == []
    empty = Settings.from_env({})
    assert empty.missing() == ["DISCORD_BOT_TOKEN", "PHANTRA_BOT_API_KEY"]
    assert empty.welcome_dm is True and empty.daily_cap == 5


def test_no_credential_value_is_in_the_repo():
    """The names are in .env.example with EMPTY values; no module holds a
    token-shaped string."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[3]
    env = (root / ".env.example").read_text()
    for name in ("DISCORD_BOT_TOKEN", "PHANTRA_BOT_API_KEY", "REDDIT_USER_AGENT",
                 "REDDIT_ALERT_WEBHOOK_URL"):
        assert re.search(rf"^{name}=\s*$", env, re.M), f"{name} must be in .env.example, empty"
    for path in (root / "bots").rglob("*.py"):
        text = path.read_text()
        # a Discord bot token is three dot-joined base64 runs, the first ~24 chars
        assert not re.search(r"[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}", text), path
        assert ("discord.com/api/" + "webhooks/") not in text, path
