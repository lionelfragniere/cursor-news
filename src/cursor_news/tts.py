from __future__ import annotations

import math
import re
import shutil
import subprocess
import wave
import asyncio
from pathlib import Path
from typing import Protocol
import unicodedata


class TTSClient(Protocol):
    def synthesize_to_wav(self, text: str, output_path: Path) -> Path:
        ...


class CoquiTTSClient:
    def __init__(
        self,
        model_name: str,
        device: str = "cpu",
        speaker_wav: str | None = None,
        speaker: str | None = None,
    ):
        self.model_name = model_name
        self.device = device
        self.speaker_wav = speaker_wav
        self.speaker = speaker
        self._tts = None

    def _load(self):
        if self._tts is None:
            try:
                from TTS.api import TTS
            except ImportError as exc:
                raise RuntimeError(
                    f"Coqui TTS est indisponible ou incompatible: {exc}. Lancez `scripts\\setup_windows.cmd` ou utilisez TTS_ENGINE=tone pour les tests."
                ) from exc
            self._tts = TTS(self.model_name).to(self.device)
        return self._tts

    def synthesize_to_wav(self, text: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tts = self._load()
        kwargs = {"text": prepare_tts_text(text), "file_path": str(output_path)}
        if "xtts" in self.model_name.lower():
            kwargs["language"] = "fr"
            if self.speaker_wav:
                kwargs["speaker_wav"] = self.speaker_wav
            elif self.speaker:
                kwargs["speaker"] = self.speaker
        tts.tts_to_file(**kwargs)
        return output_path


class ToneTTSClient:
    """Tiny local synthesizer for tests and dry runs, not for production voice quality."""

    def synthesize_to_wav(self, text: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 22050
        duration = max(1.0, min(8.0, len(text) / 120.0))
        frames = int(sample_rate * duration)
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            for index in range(frames):
                value = int(12000 * math.sin(2 * math.pi * 330 * (index / sample_rate)))
                wav.writeframesraw(value.to_bytes(2, byteorder="little", signed=True))
        return output_path


class PiperTTSClient:
    def __init__(self, model_path: str, home: Path):
        self.model_path = Path(model_path)
        if not self.model_path.is_absolute():
            self.model_path = home / self.model_path

    def synthesize_to_wav(self, text: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        piper = shutil.which("piper")
        if not piper:
            raise RuntimeError("Piper TTS est introuvable. Lancez `uv pip install piper-tts`.")
        if not self.model_path.exists():
            raise RuntimeError(f"Modèle Piper introuvable: {self.model_path}")
        subprocess.run(
            [
                piper,
                "--model",
                str(self.model_path),
                "--output_file",
                str(output_path),
                "--sentence-silence",
                "0.35",
            ],
            input=prepare_piper_text(text),
            text=True,
            encoding="utf-8",
            check=True,
            capture_output=True,
        )
        return output_path


class EdgeTTSClient:
    """Free online Microsoft Edge neural TTS. Requires network access."""

    def __init__(self, voice: str, rate: str, ffmpeg_path: str | None):
        self.voice = voice
        self.rate = rate
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg")

    def synthesize_to_wav(self, text: str, output_path: Path) -> Path:
        if not self.ffmpeg_path:
            raise RuntimeError("ffmpeg est requis pour convertir la sortie Edge TTS en WAV.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path = output_path.with_suffix(".edge.mp3")
        try:
            asyncio.run(self._save_mp3(text, mp3_path))
            subprocess.run(
                [
                    self.ffmpeg_path,
                    "-y",
                    "-i",
                    str(mp3_path),
                    "-ar",
                    "44100",
                    "-ac",
                    "1",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        finally:
            if mp3_path.exists():
                mp3_path.unlink()
        return output_path

    async def _save_mp3(self, text: str, output_path: Path) -> None:
        try:
            import edge_tts
        except ImportError as exc:
            raise RuntimeError("edge-tts est indisponible. Lancez `uv sync` ou `uv pip install edge-tts`.") from exc
        communicate = edge_tts.Communicate(prepare_online_tts_text(text), voice=self.voice, rate=self.rate)
        await communicate.save(str(output_path))


def build_tts_client(
    engine: str,
    model_name: str,
    device: str,
    speaker_wav: str | None,
    speaker: str | None,
    home: Path | None = None,
    ffmpeg_path: str | None = None,
    edge_voice: str = "fr-CH-ArianeNeural",
    edge_rate: str = "-5%",
) -> TTSClient:
    if engine == "coqui":
        return CoquiTTSClient(model_name=model_name, device=device, speaker_wav=speaker_wav, speaker=speaker)
    if engine == "edge":
        return EdgeTTSClient(edge_voice, edge_rate, ffmpeg_path)
    if engine == "piper":
        return PiperTTSClient(model_name, home or Path.cwd())
    if engine == "tone":
        return ToneTTSClient()
    raise ValueError(f"Unsupported TTS_ENGINE: {engine}")


def prepare_tts_text(text: str) -> str:
    text = normalize_tts_text(text)
    return re.sub(r"\s+", " ", text).strip()


def prepare_online_tts_text(text: str) -> str:
    text = normalize_tts_text(text)
    lines = _split_tts_lines(text, max_chars=240)
    return "\n".join(lines).strip()


def prepare_piper_text(text: str) -> str:
    text = normalize_tts_text(text)
    text = _ascii_for_piper(text)
    lines = _split_tts_lines(text)
    return "\n".join(lines).strip() + "\n"


def normalize_tts_text(text: str) -> str:
    text = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff]", "", text)
    text = re.sub(r"[\U00010000-\U0010ffff]", " ", text)
    text = _repair_mojibake_punctuation(text)
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    text = text.replace("«", "").replace("»", "").replace('"', "")
    text = text.replace("–", "-").replace("—", "-").replace("…", "...")
    text = text.replace("|", ", ")
    text = text.replace("%", " pour cent ").replace("+", " plus ")
    text = re.sub(r"\bEN DIRECT\s*[,:\-]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bM\.\s+", "monsieur ", text)
    text = re.sub(r"\bMme\s+", "madame ", text)
    text = _expand_common_acronyms(text)
    text = re.sub(r"(?<=[A-Za-zÀ-ÿ])(?=\d)", " ", text)
    text = re.sub(r"(?<=\d)(?=[A-Za-zÀ-ÿ])", " ", text)
    text = re.sub(r"\b\d+(?:er|e|ᵉ)?\b", _number_to_words, text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    return text.strip()


def _repair_mojibake_punctuation(text: str) -> str:
    replacements = {
        "â€™": "'",
        "â€˜": "'",
        "â€œ": "",
        "â€": "",
        "Â«": "",
        "Â»": "",
        "â€“": "-",
        "â€”": "-",
        "â€¦": "...",
        "Å“": "oe",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _expand_common_acronyms(text: str) -> str:
    replacements = (
        (r"\bRDC\b", "Congo"),
        (r"\bOMS\b", "Organisation mondiale de la santé"),
        (r"\bONU\b", "Organisation des Nations unies"),
        (r"\bOTAN\b", "O T A N"),
        (r"\bUE\b", "Union européenne"),
        (r"\bIA\b", "intelligence artificielle"),
        (r"\bRN\b", "Rassemblement national"),
        (r"\bUSA\b", "États-Unis"),
        (r"#MeToo\b", "Me Too"),
        (r"#Metoo\b", "Me Too"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def _ascii_for_piper(text: str) -> str:
    text = text.replace("œ", "oe").replace("Œ", "Oe")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    replacements = (
        (r"\bprevient\b", "alerte"),
        (r"\bTruth Social\b", "son reseau social"),
        (r"\btaux de letalite\b", "niveau de gravite"),
        (r"\bnotifies\b", "signales"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _split_tts_lines(text: str, max_chars: int = 180) -> list[str]:
    chunks: list[str] = []
    for paragraph in re.split(r"\n{2,}", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        for sentence in sentences:
            chunks.extend(_split_long_tts_sentence(sentence.strip(), max_chars))
    return [chunk for chunk in chunks if chunk]


def _split_long_tts_sentence(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    parts = re.split(r"(?<=[,;:])\s+", sentence)
    lines: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current} {part}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
        if len(part) <= max_chars:
            current = part
        else:
            lines.extend(_split_by_words(part, max_chars))
            current = ""
    if current:
        lines.append(current)
    return lines


def _split_by_words(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def _number_to_words(match: re.Match[str]) -> str:
    value = match.group(0)
    value = re.sub(r"(?:er|e|ᵉ)$", "", value, flags=re.IGNORECASE)
    try:
        from num2words import num2words

        return num2words(int(value), lang="fr")
    except Exception:
        return value
