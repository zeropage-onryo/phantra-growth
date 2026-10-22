"""The length probe, against a clip ffmpeg makes on the spot (no fixture
file in the repo). Skips where ffmpeg/ffprobe are absent."""
import shutil
import subprocess

import pytest

from bots.discord import clipcheck

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                  reason="ffmpeg/ffprobe not on PATH")


def test_what_counts_as_a_video():
    assert clipcheck.looks_like_video("a.MP4")
    assert clipcheck.looks_like_video("a.bin", "video/quicktime")
    assert not clipcheck.looks_like_video("a.png", "image/png")
    assert not clipcheck.looks_like_video("", None)


def test_no_ffprobe_means_unknown_not_zero(monkeypatch):
    monkeypatch.setattr(clipcheck.shutil, "which", lambda name: None)
    assert clipcheck.probe_seconds(b"\x00" * 16) is None


def test_garbage_is_unknown_not_an_exception():
    assert clipcheck.probe_seconds(b"not a video at all") is None


@needs_ffmpeg
def test_a_three_second_clip_measures_three_seconds(tmp_path):
    path = tmp_path / "t.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=10",
                    "-t", "3", "-pix_fmt", "yuv420p", str(path)], check=True)
    seconds = clipcheck.probe_seconds(path.read_bytes(), ".mp4")
    assert seconds is not None and abs(seconds - 3.0) < 0.2
