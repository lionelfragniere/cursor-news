from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .models import StyleSlot


@dataclass(frozen=True)
class ProgramSchedule:
    timezone: str
    slot_minutes: int
    default_duration_minutes: int
    styles: dict[str, StyleSlot]
    rotation: list[StyleSlot]

    @classmethod
    def load(cls, path: Path) -> "ProgramSchedule":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rotation = [_style_from_mapping(value) for value in data.get("rotation", [])]
        styles = {}
        raw_styles = data.get("styles", {})
        if isinstance(raw_styles, dict):
            styles = {
                str(minute).zfill(2): _style_from_mapping(value, default_key=str(minute))
                for minute, value in raw_styles.items()
            }
        if not rotation:
            rotation = [styles[key] for key in sorted(styles)]
        return cls(
            timezone=str(data.get("timezone", "Europe/Zurich")),
            slot_minutes=int(data.get("slot_minutes", 10)),
            default_duration_minutes=int(data.get("default_duration_minutes", 4)),
            styles=styles,
            rotation=rotation,
        )

    def floor_slot(self, now: datetime | None = None) -> datetime:
        tz = ZoneInfo(self.timezone)
        current = (now or datetime.now(tz)).astimezone(tz)
        minute = (current.minute // self.slot_minutes) * self.slot_minutes
        return current.replace(minute=minute, second=0, microsecond=0)

    def upcoming_slots(self, count: int, now: datetime | None = None) -> list[datetime]:
        start = self.floor_slot(now)
        return [start + timedelta(minutes=self.slot_minutes * offset) for offset in range(count)]

    def style_for(self, slot_start: datetime) -> StyleSlot:
        if self.rotation:
            local = slot_start.astimezone(ZoneInfo(self.timezone))
            slot_index = ((local.hour * 60) + local.minute) // self.slot_minutes
            return self.rotation[slot_index % len(self.rotation)]
        minute_key = f"{slot_start.minute:02d}"
        return self.styles.get(minute_key) or next(iter(self.styles.values()))


def _style_from_mapping(value: dict, default_key: str = "") -> StyleSlot:
    return StyleSlot(
        key=str(value.get("key", default_key)),
        label=str(value.get("label", default_key)),
        prompt=str(value.get("prompt", "")),
    )
