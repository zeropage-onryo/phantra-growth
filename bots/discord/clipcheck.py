"""The clip's length, measured on the bot's host BEFORE any upload
(2026-10-22). Discord says an attachment's size up front; its length it
does not, so the bytes are read from Discord's CDN and `ffprobe` is asked.
No ffprobe -> the length is unknown -> `looks.check_clip` refuses, in
words: the bot never uploads what it could not measure.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from typing import Optional

VIDEO_SUFFIXES = (".mp4", ".mov", ".webm", ".m4v")


def looks_like_video(filename: str, content_type: Optional[str] = None) -> bool:
    name = (filename or "").lower()
    if content_type and content_type.lower().startswith("video/"):
        return True
    return name.endswith(VIDEO_SUFFIXES)


def probe_seconds(data: bytes, suffix: str = ".mp4", *,
                  ffprobe: Optional[str] = None) -> Optional[float]:
    """The clip's duration in seconds, or None when it cannot be measured
    (no ffprobe on this host, or a file it cannot read)."""
    exe = ffprobe or shutil.which("ffprobe")
    if not exe:
        return None
    fd, path = tempfile.mkstemp(suffix=suffix or ".mp4")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        out = subprocess.run([exe, "-v", "error", "-show_entries", "format=duration",
                              "-of", "json", path], capture_output=True, text=True,
                             timeout=60, check=False)
        if out.returncode != 0:
            return None
        seconds = json.loads(out.stdout or "{}").get("format", {}).get("duration")
        return float(seconds) if seconds not in (None, "") else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
