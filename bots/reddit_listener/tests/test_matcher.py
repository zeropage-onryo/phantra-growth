from bots.reddit_listener.config import DEFAULT_PHRASES, DEFAULT_SUBREDDITS, Settings
from bots.reddit_listener.matcher import matches, normalize


def test_phrases_match_case_and_whitespace_insensitively():
    post = {"title": "What's the BEST   AI video tool right now?", "selftext": ""}
    assert matches(post, DEFAULT_PHRASES) == ["best ai video tool"]
    assert normalize("  Make  MY\nvideo ") == "make my video"


def test_body_counts_and_several_phrases_come_back_in_list_order():
    post = {"title": "help", "selftext": "I need a product demo video, something cinematic look"}
    hit = matches(post, DEFAULT_PHRASES)
    assert hit == ["need a product demo video", "product demo video", "cinematic look"]


def test_no_phrase_no_match():
    assert matches({"title": "MRR update", "selftext": "numbers"}, DEFAULT_PHRASES) == []


def test_the_briefs_phrases_and_subreddits_are_the_defaults():
    for p in ("make my video look cinematic", "best ai video tool", "higgsfield alternative",
              "need a product demo video"):
        assert p in DEFAULT_PHRASES
    assert DEFAULT_SUBREDDITS == ("aivideo", "VideoEditing", "filmmakers", "SaaS",
                                  "SideProject", "NewTubers")


def test_settings_add_configured_phrases_and_subreddits_by_env_name():
    s = Settings.from_env({"REDDIT_CLIENT_ID": "i", "REDDIT_CLIENT_SECRET": "s",
                           "REDDIT_USER_AGENT": "phantra-listener/0.1 by u/x",
                           "REDDIT_INTENT_PHRASES": "looking for a video agency | ugc ad tool",
                           "REDDIT_SUBREDDITS": "aivideo, SaaS"})
    assert s.missing() == []
    assert s.subreddits == ("aivideo", "SaaS")
    assert s.phrases[-2:] == ("looking for a video agency", "ugc ad tool")
    assert s.alert_targets() == []
    empty = Settings.from_env({})
    assert empty.missing() == ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]
    assert empty.subreddits == DEFAULT_SUBREDDITS
    mail = Settings.from_env({"REDDIT_ALERT_SMTP_HOST": "smtp.example.test",
                              "REDDIT_ALERT_FROM": "bot@example.test",
                              "REDDIT_ALERT_TO": "a@example.test,b@example.test",
                              "REDDIT_ALERT_WEBHOOK_URL": "https://discord.example.test/hook"})
    assert mail.alert_targets() == ["webhook", "email"] and mail.mail_to == ("a@example.test",
                                                                             "b@example.test")
