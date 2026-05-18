from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TIT2, TPE1

from .executables import resolve_executable
from .models import AudioResult


class AudioEncoder:
    def __init__(self, ffmpeg_path: str | None, allow_wav_fallback: bool = False):
        self.ffmpeg_path = resolve_executable(ffmpeg_path, "ffmpeg")
        self.allow_wav_fallback = allow_wav_fallback

    def encode_for_web(self, wav_path: Path, output_path: Path, title: str) -> AudioResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.ffmpeg_path:
            mp3_path = output_path.with_suffix(".mp3")
            subprocess.run(
                [
                    self.ffmpeg_path,
                    "-y",
                    "-i",
                    str(wav_path),
                    "-filter:a",
                    "loudnorm=I=-16:LRA=11:TP=-1.5",
                    "-ar",
                    "44100",
                    "-b:a",
                    "128k",
                    str(mp3_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            _write_id3(mp3_path, title)
            return AudioResult(path=mp3_path, mime_type="audio/mpeg", duration_seconds=wav_duration(wav_path))

        if self.allow_wav_fallback:
            wav_output = output_path.with_suffix(".wav")
            if wav_path.resolve() != wav_output.resolve():
                shutil.copyfile(wav_path, wav_output)
            return AudioResult(path=wav_output, mime_type="audio/wav", duration_seconds=wav_duration(wav_output))

        raise RuntimeError("ffmpeg est requis pour produire des MP3. Definissez FFMPEG_PATH ou installez ffmpeg.")


def wav_duration(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())
    except Exception:
        return None


def _write_id3(path: Path, title: str) -> None:
    try:
        try:
            tags = EasyID3(str(path))
        except Exception:
            tags = ID3()
            tags.add(TIT2(encoding=3, text=title))
            tags.add(TPE1(encoding=3, text="Cursor News"))
            tags.save(str(path))
            tags = EasyID3(str(path))
        tags["title"] = title
        tags["artist"] = "Cursor News"
        tags.save()
    except Exception:
        return
