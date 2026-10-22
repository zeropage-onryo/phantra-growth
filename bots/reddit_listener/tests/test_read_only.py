"""THE rule: across a full listener cycle, nothing is called on the Reddit
client but `subreddit(<name>)` and `.new(limit=...)`. The facade has no
write method and passes none through."""
import inspect
import re

import pytest

from bots.common.store import LocalStore
from bots.reddit_listener import facade as facade_mod
from bots.reddit_listener.config import DEFAULT_PHRASES, DEFAULT_SUBREDDITS
from bots.reddit_listener.facade import WRITE_METHODS, ReadOnlyReddit
from bots.reddit_listener.listener import cycle

WRITE_NAMES = ("reply", "submit", "comment", "upvote", "downvote", "message", "edit", "delete",
               "send", "mod", "save", "hide", "report", "award", "gild", "crosspost", "subscribe",
               "flair", "approve", "remove", "lock", "distinguish", "sticky", "block", "friend",
               "vote", "post", "contribute")


def _names_in(calls) -> set:
    return {str(c).split("(", 1)[0].replace("call.", "") for c in calls}


def test_a_full_cycle_calls_only_subreddit_and_new_on_the_client(mock_client):
    class Alert:
        name = "sink"

        def send(self, text):
            return True

    found = cycle(ReadOnlyReddit(mock_client), DEFAULT_SUBREDDITS, DEFAULT_PHRASES, LocalStore(),
                  [Alert()], limit=25)
    assert found, "the fixtures hold matches; the cycle must have read them"
    # the client itself was asked for subreddits and nothing else; each
    # subreddit mock (a fresh one per call) was asked for `new` and nothing else
    names = _names_in(mock_client.mock_calls)
    assert names == {"subreddit"}, names
    assert len(mock_client._subs) == len(DEFAULT_SUBREDDITS)
    for name, sub in mock_client._subs:
        sub_names = _names_in(sub.mock_calls)
        assert sub_names <= {"new"}, (name, sub_names)
        assert sub.new.call_args.kwargs == {"limit": 25}
    # every write name, on the client and on every subreddit and submission
    # mock the cycle touched, was never called
    for name in WRITE_NAMES:
        assert not getattr(mock_client, name).called, name
        for _, sub in mock_client._subs:
            assert not getattr(sub, name).called, name
    assert not any(any(w in str(c) for w in WRITE_NAMES) for c in mock_client.mock_calls), \
        mock_client.mock_calls


def test_submissions_are_only_read_never_called(listings):
    """Attribute reads only: a submission whose every method raises still
    goes through the facade."""
    class Loud:
        def __init__(self, ns):
            self.__dict__.update(vars(ns))

        def __getattr__(self, name):
            raise AssertionError(f"the facade touched Submission.{name}")

        def reply(self, *a, **k):
            raise AssertionError("reply was called")

    class Client:
        def subreddit(self, name):
            class Sub:
                def new(self, limit=50):
                    return [Loud(s) for s in listings[name]]
            return Sub()

    posts = ReadOnlyReddit(Client()).new_posts("aivideo", limit=3)
    assert [p["id"] for p in posts] == ["1abc01", "1abc02", "1abc03"]


@pytest.mark.parametrize("name", sorted(WRITE_METHODS))
def test_the_facade_has_no_write_method(mock_client, name):
    reddit = ReadOnlyReddit(mock_client)
    with pytest.raises(AttributeError, match="never writes"):
        getattr(reddit, name)
    assert not getattr(mock_client, name).called


def test_the_facade_passes_nothing_through_and_cannot_be_patched(mock_client):
    reddit = ReadOnlyReddit(mock_client)
    with pytest.raises(AttributeError):
        reddit.user
    with pytest.raises(AttributeError):
        reddit.inbox
    with pytest.raises(AttributeError, match="sealed"):
        reddit.reply = lambda *a: None
    assert [m for m in dir(ReadOnlyReddit) if not m.startswith("_")] == ["new_posts"]


def test_the_listener_source_names_no_write_call():
    """Belt and braces: no `.reply(`, `.submit(` ... anywhere in the
    package's own code (the facade's blocklist is a frozenset of strings,
    not a call)."""
    from pathlib import Path

    import bots.reddit_listener as pkg
    for path in Path(pkg.__file__).parent.glob("*.py"):
        if path.name == "alerts.py":
            continue            # its `.post(` is the webhook's HTTP, and it holds no Reddit object
        src = path.read_text()
        for name in WRITE_NAMES:
            if name == "send":
                continue            # alerts.send / smtp.send_message are ours, not Reddit's
            assert not re.search(rf"\.{name}\(", src), (path.name, name)
    assert "read_only = True" in inspect.getsource(facade_mod.build_client)
    assert "username" not in inspect.getsource(facade_mod.build_client).split("praw.Reddit(")[1]


def test_praw_is_imported_lazily_and_the_package_loads_without_it():
    src = inspect.getsource(facade_mod)
    assert src.count("import praw") == 1
    assert "import praw" in inspect.getsource(facade_mod.build_client)
