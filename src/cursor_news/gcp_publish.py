from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .database import Database
from .settings import Settings
from .site_export import export_site_news


def publish_to_gcp(settings: Settings, news_limit: int = 500) -> list[str]:
    bucket = _required(settings.gcp_bucket, "GCP_BUCKET")
    project = settings.gcp_project_id
    public_base_url = settings.gcp_public_base_url or public_base_url_for_bucket(bucket)
    gcloud = _resolve_gcloud(settings.gcloud_path)

    export_dir = settings.data_dir / "site_publish"
    export_dir.mkdir(parents=True, exist_ok=True)
    news_path = export_dir / "news.json"
    web_news_path = export_dir / "news-web.json"
    manifest_path = export_dir / "manifest.json"

    news_payload = export_site_news(settings, news_path, limit=news_limit, include_sports=False)
    web_news_payload = export_site_news(settings, web_news_path, limit=news_limit, include_sports=False, include_english=True)
    db = Database(settings.database_path)
    db.init()
    current = db.current_bulletin()
    bulletins_by_style = latest_bulletins_by_style(db.bulletin_history(limit=60))
    manifest = build_manifest(current, public_base_url, bulletins_by_style)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    messages = [
        _gcloud_cp(
            gcloud,
            news_path,
            f"{bucket.rstrip('/')}/current/news.json",
            project=project,
            content_type="application/json; charset=utf-8",
            cache_control="public, max-age=60",
        ),
        _gcloud_cp(
            gcloud,
            web_news_path,
            f"{bucket.rstrip('/')}/current/news-web.json",
            project=project,
            content_type="application/json; charset=utf-8",
            cache_control="public, max-age=60",
        ),
        _gcloud_cp(
            gcloud,
            manifest_path,
            f"{bucket.rstrip('/')}/current/manifest.json",
            project=project,
            content_type="application/json; charset=utf-8",
            cache_control="public, max-age=30",
        ),
    ]

    if current and current.get("audio_path"):
        audio_path = Path(str(current["audio_path"]))
        if audio_path.exists():
            messages.append(
                _gcloud_cp(
                    gcloud,
                    audio_path,
                    f"{bucket.rstrip('/')}/current/live.mp3",
                    project=project,
                    content_type="audio/mpeg",
                    cache_control="public, max-age=30",
                )
            )
            messages.append(
                _gcloud_cp(
                    gcloud,
                    audio_path,
                    f"{bucket.rstrip('/')}/bulletins/{current['id']}.mp3",
                    project=project,
                    content_type="audio/mpeg",
                    cache_control="public, max-age=31536000, immutable",
                )
            )
    for bulletin in bulletins_by_style:
        audio_path = Path(str(bulletin.get("audio_path") or ""))
        if not audio_path.exists():
            continue
        messages.append(
            _gcloud_cp(
                gcloud,
                audio_path,
                f"{bucket.rstrip('/')}/bulletins/{bulletin['id']}.mp3",
                project=project,
                content_type="audio/mpeg",
                cache_control="public, max-age=31536000, immutable",
            )
        )
    messages.append(
        f"published {news_payload['count']} android-safe news and {web_news_payload['count']} web news to {public_base_url}"
    )
    return messages


def configure_gcp_bucket_cors(settings: Settings) -> list[str]:
    bucket = _required(settings.gcp_bucket, "GCP_BUCKET")
    gcloud = _resolve_gcloud(settings.gcloud_path)
    cors_path = settings.cache_dir / "gcs-cors.json"
    cors_path.write_text(
        json.dumps(
            [
                {
                    "origin": ["*"],
                    "method": ["GET", "HEAD"],
                    "responseHeader": ["Content-Type", "Cache-Control"],
                    "maxAgeSeconds": 3600,
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    command = [gcloud, "storage", "buckets", "update", bucket, f"--cors-file={cors_path}"]
    if settings.gcp_project_id:
        command.extend(["--project", settings.gcp_project_id])
    _run(command)
    return [f"configured CORS on {bucket}"]


def latest_bulletins_by_style(history: list[dict], limit: int = 6) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    for item in history:
        style_key = str(item.get("style_key") or item.get("style_label") or "")
        if not style_key or style_key in seen:
            continue
        if not item.get("audio_path"):
            continue
        selected.append(item)
        seen.add(style_key)
        if len(selected) >= limit:
            break
    return selected


def build_manifest(current: dict | None, public_base_url: str, bulletins_by_style: list[dict] | None = None) -> dict:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bulletins = [
        _manifest_bulletin_item(item, public_base_url)
        for item in (bulletins_by_style or [])
    ]
    if not current:
        return {"generated_at": generated_at, "current": None, "bulletins_by_style": bulletins}
    return {
        "generated_at": generated_at,
        "current": _manifest_bulletin_item(current, public_base_url, current_audio=True),
        "bulletins_by_style": bulletins,
    }


def _manifest_bulletin_item(item: dict, public_base_url: str, current_audio: bool = False) -> dict:
    audio_url = (
        f"{public_base_url.rstrip('/')}/current/live.mp3"
        if current_audio
        else f"{public_base_url.rstrip('/')}/bulletins/{item['id']}.mp3"
    )
    return {
        "id": item["id"],
        "slot_start": item["slot_start"],
        "style_key": item.get("style_key", ""),
        "style": item["style_label"],
        "title": item["title"],
        "summary": item.get("summary", ""),
        "transcript": item.get("transcript", ""),
        "duration_seconds": item.get("duration_seconds"),
        "audio_url": audio_url,
        "archive_audio_url": f"{public_base_url.rstrip('/')}/bulletins/{item['id']}.mp3",
        "sources": item.get("sources", []),
    }


def public_base_url_for_bucket(bucket: str) -> str:
    clean = bucket.removeprefix("gs://").strip("/")
    return f"https://storage.googleapis.com/{clean}"


def _gcloud_cp(
    gcloud: str,
    source: Path,
    destination: str,
    *,
    project: str | None,
    content_type: str,
    cache_control: str,
) -> str:
    command = [
        gcloud,
        "storage",
        "cp",
        str(source),
        destination,
        f"--content-type={content_type}",
        f"--cache-control={cache_control}",
    ]
    if project:
        command.extend(["--project", project])
    _run(command)
    return f"uploaded {source.name} -> {destination}"


def _resolve_gcloud(value: str) -> str:
    candidates = [value, "gcloud.cmd", "gcloud"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError("gcloud CLI introuvable. Installez Google Cloud SDK ou definissez GCLOUD_PATH.")


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def _required(value: str | None, name: str) -> str:
    if not value:
        raise RuntimeError(f"{name} est requis pour publier vers GCP.")
    return value
