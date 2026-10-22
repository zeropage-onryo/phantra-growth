"""Which posts mean intent (2026-10-22): a phrase of the list found in the
title or body, case- and whitespace-insensitively."""
from __future__ import annotations

import re
from typing import Iterable

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _WS.sub(" ", (text or "").lower()).strip()


def matches(post: dict, phrases: Iterable[str]) -> list[str]:
    """The phrases found in this post, in list order; [] when none."""
    hay = normalize(f"{post.get('title', '')} \n {post.get('selftext', '')}")
    return [p for p in phrases if p and normalize(p) in hay]
