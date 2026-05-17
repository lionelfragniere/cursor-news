from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .database import Database
from .settings import Settings


@dataclass(frozen=True)
class StreamPlan:
    playlist_path: Path
    audio_paths: list[Path]
    command: list[str]
    redacted_command: list[str]


class InfomaniakIcecastStreamer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.database_path)

    def plan(self, limit: int = 12, loop: bool = True, duration_seconds: int | None = None) -> StreamPlan:
        ffmpeg_path = self._ffmpeg_path()
        audio_paths = self._audio_paths(limit)
        if not audio_paths:
            raise RuntimeError("Aucun bulletin audio pret a diffuser.")

        playlist_path = self.settings.cache_dir / "infomaniak-stream-playlist.txt"
        playlist_path.write_text(concat_playlist_text(audio_paths), encoding="utf-8")

        command = build_ffmpeg_icecast_command(
            ffmpeg_path=ffmpeg_path,
            playlist_path=playlist_path,
            host=_required(self.settings.infomaniak_stream_host, "INFOMANIAK_STREAM_HOST"),
            port=self.settings.infomaniak_stream_port,
            mount=_required(self.settings.infomaniak_stream_mount, "INFOMANIAK_STREAM_MOUNT"),
            username=self.settings.infomaniak_stream_username,
            password=_required(self.settings.infomaniak_stream_password, "INFOMANIAK_STREAM_PASSWORD"),
            bitrate=self.settings.infomaniak_stream_bitrate,
            sample_rate=self.settings.infomaniak_stream_sample_rate,
            loop=loop,
            duration_seconds=duration_seconds,
        )
        return StreamPlan(
            playlist_path=playlist_path,
            audio_paths=audio_paths,
            command=command,
            redacted_command=redact_command(command, self.settings.infomaniak_stream_password),
        )

    def run(self, limit: int = 12, loop: bool = True, duration_seconds: int | None = None) -> int:
        plan = self.plan(limit=limit, loop=loop, duration_seconds=duration_seconds)
        process = subprocess.run(plan.command)
        return int(process.returncode)

    def _ffmpeg_path(self) -> str:
        ffmpeg_path = self.settings.ffmpeg_path or shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError("ffmpeg est requis pour diffuser vers Infomaniak.")
        if not Path(ffmpeg_path).exists() and not shutil.which(ffmpeg_path):
            raise RuntimeError(f"ffmpeg introuvable: {ffmpeg_path}")
        return str(ffmpeg_path)

    def _audio_paths(self, limit: int) -> list[Path]:
        self.db.init()
        items = list(reversed(self.db.bulletin_history(limit=max(1, limit))))
        paths: list[Path] = []
        for item in items:
            value = item.get("audio_path")
            if not value:
                continue
            path = Path(value)
            if path.exists() and path.suffix.lower() in {".mp3", ".aac", ".wav", ".m4a"}:
                paths.append(path.resolve())
        return paths


def build_ffmpeg_icecast_command(
    *,
    ffmpeg_path: str,
    playlist_path: Path,
    host: str,
    port: int,
    mount: str,
    username: str,
    password: str,
    bitrate: str,
    sample_rate: int,
    loop: bool,
    duration_seconds: int | None = None,
) -> list[str]:
    command = [
        ffmpeg_path,
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "warning",
        "-re",
    ]
    if loop:
        command.extend(["-stream_loop", "-1"])
    command.extend(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(playlist_path),
            "-vn",
            "-ac",
            "2",
            "-ar",
            str(sample_rate),
            "-c:a",
            "aac",
            "-b:a",
            bitrate,
            "-content_type",
            "audio/aac",
            "-ice_name",
            "Cursor News",
            "-ice_description",
            "Cursor News - flashs d'actualite generes par IA",
            "-ice_genre",
            "News",
            "-ice_public",
            "0",
            "-password",
            password,
        ]
    )
    if duration_seconds:
        command.extend(["-t", str(duration_seconds)])
    command.extend(["-f", "adts", build_icecast_url(host, port, mount, username)])
    return command


def build_icecast_url(host: str, port: int, mount: str, username: str) -> str:
    clean_mount = mount if mount.startswith("/") else f"/{mount}"
    return f"icecast://{quote(username, safe='')}@{host}:{port}{clean_mount}"


def concat_playlist_text(paths: list[Path]) -> str:
    lines = [f"file '{_escape_concat_path(path)}'" for path in paths]
    return "\n".join(lines) + "\n"


def redact_command(command: list[str], secret: str | None) -> list[str]:
    if not secret:
        return list(command)
    return ["***" if part == secret else part.replace(secret, "***") for part in command]


def _escape_concat_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")


def _required(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(f"{name} est requis pour diffuser vers Infomaniak.")
    return value
