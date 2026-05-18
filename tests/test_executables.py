from pathlib import Path

from cursor_news.executables import resolve_executable


def test_resolve_executable_falls_back_when_windows_path_is_missing(monkeypatch):
    monkeypatch.setattr("cursor_news.executables.shutil.which", lambda name: "/usr/bin/ffmpeg")

    resolved = resolve_executable("missing-tools\\ffmpeg\\bin\\ffmpeg.exe", "ffmpeg")

    assert resolved == "/usr/bin/ffmpeg"


def test_resolve_executable_keeps_existing_configured_path(tmp_path: Path, monkeypatch):
    executable = tmp_path / "ffmpeg"
    executable.write_text("", encoding="utf-8")
    monkeypatch.setattr("cursor_news.executables.shutil.which", lambda name: "/usr/bin/ffmpeg")

    resolved = resolve_executable(str(executable), "ffmpeg")

    assert resolved == str(executable)
