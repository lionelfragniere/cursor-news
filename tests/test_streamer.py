from pathlib import Path

from cursor_news.streamer import build_ffmpeg_icecast_command, build_icecast_url, concat_playlist_text, redact_command


def test_build_icecast_url_keeps_password_out_of_url():
    url = build_icecast_url("radio.example.test", 80, "/mount.aac", "source")
    assert url == "icecast://source@radio.example.test:80/mount.aac"


def test_concat_playlist_text_uses_absolute_forward_slash_paths(tmp_path: Path):
    audio = tmp_path / "Cursor News" / "bulletin.mp3"
    audio.parent.mkdir()
    audio.write_bytes(b"fake")
    text = concat_playlist_text([audio])
    assert text.startswith("file '")
    assert "\\\\" not in text
    assert "bulletin.mp3" in text


def test_ffmpeg_command_redacts_stream_password(tmp_path: Path):
    command = build_ffmpeg_icecast_command(
        ffmpeg_path="ffmpeg",
        playlist_path=tmp_path / "playlist.txt",
        host="radio.example.test",
        port=80,
        mount="mount.aac",
        username="source",
        password="secret-password",
        bitrate="128k",
        sample_rate=44100,
        loop=True,
        duration_seconds=10,
    )
    redacted = redact_command(command, "secret-password")
    assert "secret-password" in command
    assert "secret-password" not in " ".join(redacted)
    assert "icecast://source@radio.example.test:80/mount.aac" in command
    assert "-stream_loop" in command
