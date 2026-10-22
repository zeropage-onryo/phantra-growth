"""Fixtures: the hand-written listings as PRAW-shaped objects, and a
MagicMock Reddit client that serves them so every call is recorded."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
LISTINGS = {"aivideo": "aivideo_new.json", "SaaS": "saas_new.json", "NewTubers": "newtubers_new.json"}


def submissions_from(name: str) -> list[SimpleNamespace]:
    """A fixture file -> objects with PRAW Submission's attributes
    (author is an object with .name, or None for a deleted account)."""
    rows = json.loads((FIXTURES / name).read_text())
    out = []
    for row in rows:
        author = row.get("author")
        out.append(SimpleNamespace(**{**row, "author": SimpleNamespace(**author) if author else None}))
    return out


@pytest.fixture
def listings() -> dict[str, list[SimpleNamespace]]:
    return {sub: submissions_from(file) for sub, file in LISTINGS.items()}


@pytest.fixture
def mock_client(listings) -> MagicMock:
    """praw.Reddit as a MagicMock: `.subreddit(name).new(limit=...)` yields
    the fixture; every other call lands on the mock and is recorded."""
    client = MagicMock(name="praw.Reddit")

    def subreddit(name):
        sub = MagicMock(name=f"subreddit:{name}")
        sub.new.side_effect = lambda limit=50: list(listings.get(name, []))[:limit]
        client._subs.append((name, sub))
        return sub

    client._subs = []
    client.subreddit.side_effect = subreddit
    return client
