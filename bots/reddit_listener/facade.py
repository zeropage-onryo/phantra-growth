"""The read-only face of a Reddit client (2026-10-22).

`ReadOnlyReddit` is the ONLY thing the listener holds. It has reading
methods and nothing else: no `reply`, `submit`, `comment`, `upvote`,
`downvote`, `message`, `edit`, `delete`, `send`, `mod`, no attribute
pass-through to the client underneath (`__getattr__` refuses by name).
What comes back is plain dicts, so nothing downstream can reach a PRAW
object and call something on it. The listener's test runs a whole cycle
over a MagicMock client and asserts the only calls were
`subreddit(<name>)` and `.new(limit=...)`.
"""
from __future__ import annotations

from typing import Any, Iterable

WRITE_METHODS = frozenset({
    "reply", "submit", "comment", "upvote", "downvote", "clear_vote", "vote", "message",
    "edit", "delete", "send", "mod", "save", "unsave", "hide", "unhide", "report", "award",
    "gild", "crosspost", "subscribe", "unsubscribe", "flair", "approve", "remove", "lock",
    "unlock", "distinguish", "undistinguish", "sticky", "block", "friend", "unfriend",
    "submit_image", "submit_video", "submit_poll", "submit_gallery", "contribute", "post",
})

POST_FIELDS = ("id", "title", "selftext", "permalink", "url", "created_utc", "score",
               "num_comments", "is_self", "link_flair_text", "over_18")


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _post_of(submission: Any, subreddit: str) -> dict:
    """A PRAW Submission (or anything shaped like one) -> a plain dict. Only
    attributes are READ; nothing is called on the submission."""
    post = {name: getattr(submission, name, None) for name in POST_FIELDS}
    author = getattr(submission, "author", None)
    post["author"] = _text(getattr(author, "name", None) if author is not None else None)
    post["subreddit"] = subreddit
    post["id"] = _text(post["id"])
    post["title"] = _text(post["title"])
    post["selftext"] = _text(post["selftext"])
    link = _text(post.get("permalink"))
    post["link"] = f"https://www.reddit.com{link}" if link.startswith("/") else link
    return post


class ReadOnlyReddit:
    """Reading only. `client` is a praw.Reddit (or a fake with the same
    two calls)."""

    __slots__ = ("_client",)

    def __init__(self, client: Any):
        object.__setattr__(self, "_client", client)

    def new_posts(self, subreddit: str, limit: int = 50) -> list[dict]:
        """The newest `limit` posts of one subreddit, as plain dicts."""
        listing: Iterable[Any] = self._client.subreddit(subreddit).new(limit=limit)
        return [_post_of(s, subreddit) for s in listing]

    def __getattr__(self, name: str):
        if name in WRITE_METHODS:
            raise AttributeError(f"ReadOnlyReddit has no {name}: this listener never writes")
        raise AttributeError(f"ReadOnlyReddit exposes new_posts only, not {name}")

    def __setattr__(self, name, value):
        raise AttributeError("ReadOnlyReddit is sealed")


def build_client(client_id: str, client_secret: str, user_agent: str) -> ReadOnlyReddit:
    """A PRAW client in read-only mode (no username, no password, no
    refresh token: the app can only read), behind the facade. praw is
    imported here so the rest of the package loads without it."""
    import praw
    reddit = praw.Reddit(client_id=client_id, client_secret=client_secret,
                         user_agent=user_agent)
    reddit.read_only = True
    return ReadOnlyReddit(reddit)
