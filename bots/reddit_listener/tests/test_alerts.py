"""Where alerts go, without sending any: a webhook over MockTransport, an
email through a fake SMTP class, stdout."""
import io
import json

import httpx

from bots.reddit_listener.alerts import EmailAlert, StdoutAlert, WebhookAlert, format_alert
from bots.reddit_listener.config import Settings
from bots.reddit_listener.listener import alerters_for

POST = {"subreddit": "SaaS", "author": "founder_amy", "title": "Need a product demo video",
        "selftext": "Launching on PH next month.\nWhat do people use?",
        "link": "https://www.reddit.com/r/SaaS/comments/2def01/"}


def test_format_alert_is_four_lines_with_a_flattened_body():
    text = format_alert(POST, ["need a product demo video"])
    assert text.splitlines() == ["r/SaaS · u/founder_amy · matched: need a product demo video",
                                 "**Need a product demo video**",
                                 "Launching on PH next month. What do people use?",
                                 "https://www.reddit.com/r/SaaS/comments/2def01/"]
    long = format_alert({**POST, "selftext": "x" * 400}, ["p"])
    assert "..." in long and len(long.splitlines()[2]) == 280


def test_webhook_posts_the_text_with_mentions_off():
    seen = []

    def handler(request):
        seen.append((str(request.url), json.loads(request.content)))
        return httpx.Response(204)

    hook = WebhookAlert("https://discord.example.test/api/hooks/1/abc",
                        client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert hook.send("hello") is True
    assert seen == [("https://discord.example.test/api/hooks/1/abc",
                     {"content": "hello", "allowed_mentions": {"parse": []}})]


def test_webhook_failure_is_false_not_an_exception():
    hook = WebhookAlert("https://discord.example.test/hook",
                        client=httpx.Client(transport=httpx.MockTransport(
                            lambda r: httpx.Response(429))))
    assert hook.send("x") is False


def test_email_goes_through_the_injected_smtp():
    log = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            log.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            log.append(("quit",))

        def starttls(self):
            log.append(("tls",))

        def login(self, user, password):
            log.append(("login", user))

        def send_message(self, msg):
            log.append(("send", msg["From"], msg["To"], msg["Subject"], msg.get_content().strip()))

    mail = EmailAlert("smtp.example.test", 587, "u", "p", "bot@example.test",
                      ["a@example.test", "b@example.test"], smtp=FakeSMTP)
    assert mail.send("a post") is True
    assert log == [("connect", "smtp.example.test", 587), ("tls",), ("login", "u"),
                   ("send", "bot@example.test", "a@example.test, b@example.test",
                    "Phantra: a Reddit post worth a look", "a post"), ("quit",)]


def test_stdout_is_the_alerter_when_nothing_is_configured():
    s = Settings.from_env({})
    out = alerters_for(s)
    assert [a.name for a in out] == ["stdout"]
    buf = io.StringIO()
    assert StdoutAlert(buf).send("hi") and buf.getvalue() == "hi\n\n"
    both = alerters_for(Settings.from_env({"REDDIT_ALERT_WEBHOOK_URL": "https://h.example.test/x",
                                           "REDDIT_ALERT_SMTP_HOST": "smtp.example.test",
                                           "REDDIT_ALERT_FROM": "b@example.test",
                                           "REDDIT_ALERT_TO": "a@example.test"}))
    assert [a.name for a in both] == ["webhook", "email"]


def test_main_refuses_without_the_names(monkeypatch, capsys):
    from bots.reddit_listener.listener import main
    assert main(["--once"]) == 2
    err = capsys.readouterr().err
    assert "REDDIT_CLIENT_ID" in err and "REDDIT_USER_AGENT" in err
