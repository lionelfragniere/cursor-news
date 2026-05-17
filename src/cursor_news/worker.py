from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler

from .pipeline import CursorNewsPipeline
from .settings import load_settings


def run_worker() -> None:
    settings = load_settings()
    pipeline = CursorNewsPipeline(settings)
    pipeline.init_db()
    pipeline.ingest_once()
    pipeline.generate_buffer()

    scheduler = BlockingScheduler(timezone=settings.timezone)
    scheduler.add_job(pipeline.ingest_once, "interval", minutes=settings.ingest_interval_minutes, id="ingest")
    scheduler.add_job(pipeline.generate_buffer, "interval", seconds=settings.generate_interval_seconds, id="generate")
    scheduler.start()
