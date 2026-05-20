from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .database import Database
from .schedule import ProgramSchedule
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
    web_extended_news_path = export_dir / "news-web-extended.json"
    manifest_path = export_dir / "manifest.json"

    news_payload = export_site_news(settings, news_path, limit=news_limit, include_sports=False)
    web_news_payload = export_site_news(settings, web_news_path, limit=news_limit, include_sports=False, include_english=True)
    web_extended_news_payload = export_site_news(
        settings,
        web_extended_news_path,
        limit=news_limit,
        include_sports=False,
        include_english=True,
        include_german=True,
    )
    db = Database(settings.database_path)
    db.init()
    current = db.current_bulletin()
    allowed_topic_keys = {style.key for style in ProgramSchedule.load(settings.schedule_path).rotation}
    bulletins_by_topic = latest_bulletins_by_topic(
        db.bulletin_history(limit=240),
        limit=settings.gcp_topic_archive_limit,
        allowed_keys=allowed_topic_keys,
    )
    manifest = build_manifest(current, public_base_url, bulletins_by_topic)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    state_path = export_dir / "publish-state.json"
    publish_state = _load_publish_state(state_path)

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
            web_extended_news_path,
            f"{bucket.rstrip('/')}/current/news-web-extended.json",
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

    bucket_root = bucket.rstrip("/")
    uploaded_ids: set[str] = set()
    if current and current.get("audio_path"):
        audio_path = Path(str(current["audio_path"]))
        if audio_path.exists():
            if publish_state.get("current_live_id") == current["id"]:
                messages.append(f"skipped live.mp3, unchanged current bulletin {current['id']}")
            else:
                messages.append(
                    _gcloud_cp(
                        gcloud,
                        audio_path,
                        f"{bucket_root}/current/live.mp3",
                        project=project,
                        content_type="audio/mpeg",
                        cache_control="public, max-age=30",
                    )
                )
                publish_state["current_live_id"] = current["id"]
            messages.append(
                _upload_bulletin_if_needed(gcloud, bucket_root, current, project=project, state=publish_state)
            )
            uploaded_ids.add(str(current["id"]))
    for bulletin in bulletins_by_topic:
        if str(bulletin.get("id")) in uploaded_ids:
            continue
        audio_path = Path(str(bulletin.get("audio_path") or ""))
        if not audio_path.exists():
            continue
        messages.append(_upload_bulletin_if_needed(gcloud, bucket_root, bulletin, project=project, state=publish_state))
        uploaded_ids.add(str(bulletin["id"]))
    keep_ids = {str(item.get("id")) for item in bulletins_by_topic if item.get("id")}
    if current and current.get("id"):
        keep_ids.add(str(current["id"]))
    messages.extend(_delete_stale_bulletins(gcloud, bucket_root, keep_ids, project=project))
    publish_state["uploaded_bulletins"] = sorted(
        bulletin_id for bulletin_id in (publish_state.get("uploaded_bulletins") or []) if bulletin_id in keep_ids
    )
    publish_state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _save_publish_state(state_path, publish_state)
    messages.append(
        f"published {news_payload['count']} android-safe news, {web_news_payload['count']} english web news and {web_extended_news_payload['count']} extended web news to {public_base_url}"
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
    return latest_bulletins_by_topic(history, limit=limit)


def latest_bulletins_by_topic(
    history: list[dict],
    limit: int = 6,
    allowed_keys: set[str] | None = None,
) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    for item in history:
        style_key = str(item.get("style_key") or item.get("style_label") or "")
        if not style_key or style_key in seen:
            continue
        if allowed_keys is not None and style_key not in allowed_keys:
            continue
        if not item.get("audio_path"):
            continue
        selected.append(item)
        seen.add(style_key)
        if len(selected) >= limit:
            break
    return selected


def recent_bulletins_by_topic(
    history: list[dict],
    retention_hours: int = 2,
    now: datetime | None = None,
    limit: int = 24,
) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    cutoff = current - timedelta(hours=retention_hours)
    recent = []
    for item in history:
        slot_start = _parse_datetime(str(item.get("slot_start") or ""))
        if not slot_start or slot_start < cutoff:
            continue
        recent.append(item)
    return latest_bulletins_by_topic(recent, limit=limit)


def build_manifest(current: dict | None, public_base_url: str, bulletins_by_topic: list[dict] | None = None) -> dict:
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    bulletins = [
        _manifest_bulletin_item(item, public_base_url)
        for item in (bulletins_by_topic or [])
    ]
    if not current:
        return {
            "generated_at": generated_at,
            "current": None,
            "bulletins_by_topic": bulletins,
            "bulletins_by_style": bulletins,
        }
    return {
        "generated_at": generated_at,
        "current": _manifest_bulletin_item(current, public_base_url, current_audio=True),
        "bulletins_by_topic": bulletins,
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


def _upload_bulletin_if_needed(
    gcloud: str,
    bucket_root: str,
    bulletin: dict,
    *,
    project: str | None,
    state: dict,
) -> str:
    bulletin_id = str(bulletin["id"])
    destination = f"{bucket_root}/bulletins/{bulletin_id}.mp3"
    uploaded = set(state.get("uploaded_bulletins") or [])
    if bulletin_id in uploaded and _gcloud_exists(gcloud, destination, project=project):
        return f"skipped existing bulletin {bulletin_id}"
    message = _gcloud_cp(
        gcloud,
        Path(str(bulletin["audio_path"])),
        destination,
        project=project,
        content_type="audio/mpeg",
        cache_control="public, max-age=600",
    )
    uploaded.add(bulletin_id)
    state["uploaded_bulletins"] = sorted(uploaded)
    return message


def _delete_stale_bulletins(gcloud: str, bucket_root: str, keep_ids: set[str], *, project: str | None) -> list[str]:
    messages: list[str] = []
    for bulletin_id in _remote_bulletin_ids(gcloud, bucket_root, project=project):
        if bulletin_id in keep_ids:
            continue
        destination = f"{bucket_root}/bulletins/{bulletin_id}.mp3"
        _gcloud_rm(gcloud, destination, project=project)
        messages.append(f"deleted stale bulletin {bulletin_id}")
    return messages


def _remote_bulletin_ids(gcloud: str, bucket_root: str, *, project: str | None) -> set[str]:
    command = [gcloud, "storage", "ls", f"{bucket_root}/bulletins/*.mp3"]
    if project:
        command.extend(["--project", project])
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        return set()
    ids: set[str] = set()
    for line in result.stdout.splitlines():
        name = line.rstrip("/").rsplit("/", 1)[-1]
        if name.endswith(".mp3"):
            ids.add(name[:-4])
    return ids


def _gcloud_exists(gcloud: str, destination: str, *, project: str | None) -> bool:
    command = [gcloud, "storage", "ls", destination]
    if project:
        command.extend(["--project", project])
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0


def _gcloud_rm(gcloud: str, destination: str, *, project: str | None) -> None:
    command = [gcloud, "storage", "rm", destination]
    if project:
        command.extend(["--project", project])
    _run(command)


def _load_publish_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"uploaded_bulletins": []}


def _save_publish_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
