from datetime import datetime
from pathlib import Path

from cursor_news.schedule import ProgramSchedule


def test_schedule_floors_to_hour():
    schedule = ProgramSchedule.load(Path("config/schedule.yml"))
    slot = schedule.floor_slot(datetime.fromisoformat("2026-05-17T08:37:12+02:00"))
    assert slot.minute == 0
    assert schedule.style_for(slot).key == "valais"


def test_schedule_uses_hourly_topic_rotation():
    schedule = ProgramSchedule.load(Path("config/schedule.yml"))
    keys = [
        schedule.style_for(datetime.fromisoformat(f"2026-05-17T{hour:02d}:00:00+02:00")).key
        for hour in range(7)
    ]
    assert keys == [
        "suisse_romande",
        "valais",
        "suisse",
        "international",
        "un_relevant",
        "international_english",
        "security_world",
    ]
