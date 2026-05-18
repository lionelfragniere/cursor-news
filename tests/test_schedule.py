from datetime import datetime
from pathlib import Path

from cursor_news.schedule import ProgramSchedule


def test_schedule_floors_to_ten_minutes():
    schedule = ProgramSchedule.load(Path("config/schedule.yml"))
    slot = schedule.floor_slot(datetime.fromisoformat("2026-05-17T08:37:12+02:00"))
    assert slot.minute == 30
    assert schedule.style_for(slot).key == "anxiogene"


def test_schedule_uses_explicit_ten_minute_grid():
    schedule = ProgramSchedule.load(Path("config/schedule.yml"))
    keys = [
        schedule.style_for(datetime.fromisoformat(f"2026-05-17T09:{minute:02d}:00+02:00")).key
        for minute in (0, 10, 20, 30, 40, 50)
    ]
    assert keys == ["journaliste", "pote", "non_anxiogene", "anxiogene", "enfant", "contexte"]
