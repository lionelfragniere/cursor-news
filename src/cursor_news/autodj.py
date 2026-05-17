from __future__ import annotations

import csv
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .database import Database
from .settings import Settings


SLOT_PLAN = [
    ("00", "journaliste", "Journaliste"),
    ("10", "pote", "Pote"),
    ("20", "non_anxiogene", "Non anxiogène"),
    ("30", "anxiogene", "Anxiogène"),
    ("40", "enfant", "Pour enfant"),
    ("50", "journaliste", "Récap journaliste"),
]


@dataclass(frozen=True)
class AutoDJExport:
    export_dir: Path
    slot_files: list[Path]
    loop_file: Path | None
    schedule_csv: Path
    readme: Path


class AutoDJExporter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db = Database(settings.database_path)

    def export(self, output_dir: Path | None = None, build_hour_loop: bool = True) -> AutoDJExport:
        self.db.init()
        root = output_dir or self.settings.data_dir / "autodj" / datetime.now().strftime("%Y%m%d-%H%M%S")
        root.mkdir(parents=True, exist_ok=True)

        by_style = self._latest_ready_by_style()
        slot_files: list[Path] = []
        schedule_rows: list[dict[str, str]] = []
        for minute, style_key, label in SLOT_PLAN:
            bulletin = by_style.get(style_key)
            if not bulletin:
                continue
            source = Path(str(bulletin["audio_path"]))
            if not source.exists():
                continue
            destination = root / f"CursorNews_{minute}_{style_key}.mp3"
            shutil.copyfile(source, destination)
            slot_files.append(destination)
            schedule_rows.append(
                {
                    "minute": minute,
                    "style": label,
                    "file": destination.name,
                    "source_bulletin": str(bulletin["id"]),
                    "title": str(bulletin["title"]),
                }
            )

        if len(slot_files) < len(SLOT_PLAN):
            missing = len(SLOT_PLAN) - len(slot_files)
            raise RuntimeError(f"Export Auto DJ incomplet: {missing} fichier(s) de creneau manquant(s).")

        schedule_csv = root / "schedule_10min.csv"
        write_schedule_csv(schedule_csv, schedule_rows)

        loop_file = None
        if build_hour_loop:
            loop_file = root / "CursorNews_1h_loop.mp3"
            build_one_hour_loop(self._ffmpeg_path(), slot_files, root, loop_file)

        readme = root / "README_UPLOAD.md"
        readme.write_text(upload_readme(loop_file, slot_files), encoding="utf-8")
        return AutoDJExport(root, slot_files, loop_file, schedule_csv, readme)

    def _latest_ready_by_style(self) -> dict[str, dict]:
        items = self.db.bulletin_history(limit=200)
        result: dict[str, dict] = {}
        for item in items:
            style = _style_key_from_bulletin(item)
            if style and style not in result and item.get("audio_path"):
                result[style] = item
        return result

    def _ffmpeg_path(self) -> str:
        ffmpeg_path = self.settings.ffmpeg_path or shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise RuntimeError("ffmpeg est requis pour creer la boucle Auto DJ d'une heure.")
        return str(ffmpeg_path)


def build_one_hour_loop(ffmpeg_path: str, slot_files: list[Path], work_dir: Path, output_file: Path) -> None:
    segment_dir = work_dir / "segments_10min"
    segment_dir.mkdir(parents=True, exist_ok=True)
    segment_files: list[Path] = []
    for index, source in enumerate(slot_files):
        segment = segment_dir / f"{index:02d}_{source.stem}_10min.mp3"
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-af",
                "apad=whole_dur=600",
                "-t",
                "600",
                "-ar",
                "44100",
                "-ac",
                "2",
                "-b:a",
                "128k",
                str(segment),
            ],
            check=True,
        )
        segment_files.append(segment)

    concat_file = work_dir / "loop_concat.txt"
    concat_file.write_text(_concat_text(segment_files), encoding="utf-8")
    subprocess.run(
        [
            ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(output_file),
        ],
        check=True,
    )


def write_schedule_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["minute", "style", "file", "source_bulletin", "title"])
        writer.writeheader()
        writer.writerows(rows)


def upload_readme(loop_file: Path | None, slot_files: list[Path]) -> str:
    loop_name = loop_file.name if loop_file else "non genere"
    slot_list = "\n".join(f"- {path.name}" for path in slot_files)
    return f"""# Cursor News - pack Auto DJ

## Option recommandee

Importer `{loop_name}` dans l'espace AOD Infomaniak, puis creer une playlist Auto DJ qui boucle ce fichier.
Pour garder les tops horaires alignes, demarrer ou programmer la playlist au debut d'une heure.

Le fichier d'une heure contient les tops suivants:

- 00: Journaliste
- 10: Pote
- 20: Non anxiogene
- 30: Anxiogene
- 40: Pour enfant
- 50: Recap journaliste

## Option avancee

Importer les fichiers individuels et les programmer dans le calendrier Auto DJ toutes les 10 minutes:

{slot_list}

## Notes

- Infomaniak accepte les fichiers audio AOD en MP3/AAC.
- Une fois les fichiers importes et Auto DJ active, le PC local peut etre eteint.
- Pour publier de nouvelles actualites, il faut regenerer un pack et remplacer ou reprogrammer les fichiers dans l'AOD.
"""


def _style_key_from_bulletin(item: dict) -> str:
    bulletin_id = str(item.get("id") or "")
    if "-non_anxiogene-" in bulletin_id:
        return "non_anxiogene"
    for key in ("journaliste", "pote", "anxiogene", "enfant"):
        if f"-{key}-" in bulletin_id:
            return key
    label = str(item.get("style_label") or "").casefold()
    if "non" in label and "anxi" in label:
        return "non_anxiogene"
    if "anxi" in label:
        return "anxiogene"
    if "enfant" in label:
        return "enfant"
    if "pote" in label:
        return "pote"
    if "journaliste" in label:
        return "journaliste"
    return ""


def _concat_text(paths: list[Path]) -> str:
    lines = []
    for path in paths:
        normalized = str(path.resolve()).replace("\\", "/")
        lines.append(f"file '{normalized}'")
    return "\n".join(lines) + "\n"
