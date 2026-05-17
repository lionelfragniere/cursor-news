from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import Database
from .settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    db = Database(settings.database_path)
    db.init()

    app = FastAPI(title="Cursor News", version="0.1.0")
    app.state.settings = settings
    app.state.db = db

    app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

    @app.get("/")
    def index():
        return FileResponse(settings.static_dir / "index.html")

    @app.get("/api/current")
    def current():
        item = db.current_bulletin()
        if not item:
            return {"has_bulletin": False}
        return _bulletin_payload(settings, item)

    @app.get("/api/history")
    def history(limit: int = 12):
        return [_bulletin_payload(settings, item) for item in db.bulletin_history(limit=limit)]

    @app.get("/api/articles")
    def articles(limit: int = 50, include_sports: bool = True):
        limit = max(1, min(limit, 500))
        return db.article_archive(limit=limit, include_sports=include_sports)

    @app.get("/api/bulletins/{bulletin_id}")
    def bulletin(bulletin_id: str):
        item = db.bulletin_by_id(bulletin_id)
        if not item:
            raise HTTPException(status_code=404, detail="Bulletin not found")
        return _bulletin_payload(settings, item)

    @app.get("/api/status")
    def status():
        return db.status_snapshot()

    @app.get("/api/stream")
    def stream():
        url = settings.infomaniak_public_stream_url
        stream_type = "hls" if url and url.lower().split("?")[0].endswith(".m3u8") else "audio"
        return {
            "enabled": bool(url),
            "url": url,
            "type": stream_type,
            "label": "Direct Infomaniak",
        }

    @app.get("/audio/{filename}")
    def audio(filename: str):
        path = (settings.audio_dir / filename).resolve()
        audio_root = settings.audio_dir.resolve()
        if audio_root not in path.parents and path != audio_root:
            raise HTTPException(status_code=404, detail="Audio not found")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Audio not found")
        media_type = "audio/mpeg" if path.suffix.lower() == ".mp3" else "audio/wav"
        return FileResponse(
            path,
            media_type=media_type,
            filename=path.name,
            headers={"Cache-Control": "no-store"},
        )

    return app


def _bulletin_payload(settings: Settings, item: dict) -> dict:
    audio_path = item.get("audio_path")
    audio_url = None
    if audio_path:
        path = Path(audio_path)
        version = ""
        if path.exists():
            version = f"?v={int(path.stat().st_mtime)}"
        audio_url = f"/audio/{path.name}{version}"
    return {
        "has_bulletin": True,
        "id": item["id"],
        "slot_start": item["slot_start"],
        "style": item["style_label"],
        "title": item["title"],
        "summary": item.get("summary", ""),
        "transcript": item.get("transcript", ""),
        "audio_url": audio_url,
        "audio_mime_type": item.get("audio_mime_type"),
        "duration_seconds": item.get("duration_seconds"),
        "sources": item.get("sources", []),
    }
