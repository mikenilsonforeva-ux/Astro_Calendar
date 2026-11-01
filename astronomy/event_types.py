"""Тип «астрономическое событие» и категории календаря."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

CAT_MOON_PHASE = "moon_phase"
CAT_SEASON = "season"
CAT_APSIDES = "apsides"
CAT_PLANET = "planet"
CAT_ECLIPSE = "eclipse"
CAT_METEOR = "meteor"

CATEGORY_NAMES = {
    CAT_MOON_PHASE: "Фазы Луны",
    CAT_SEASON: "Равноденствия и солнцестояния",
    CAT_APSIDES: "Перигей и апогей Луны",
    CAT_PLANET: "Планеты",
    CAT_ECLIPSE: "Затмения",
    CAT_METEOR: "Метеорные потоки",
}


@dataclass
class AstroEvent:
    category: str
    title: str
    utc_time: datetime
    body: str = ""
    description: str = ""
    params: dict = field(default_factory=dict)
    source: str = ""
    visibility: str = ""       # заполняется для выбранного места наблюдения
    is_global: bool = True     # глобальное событие (не равно «видно отсюда»)

    @property
    def all_day(self) -> bool:
        return bool(self.params.get("all_day"))

    def to_row(self) -> dict:
        return {
            "category": self.category,
            "body": self.body,
            "title": self.title,
            "description": self.description,
            "utc_time": self.utc_time.strftime("%Y-%m-%dT%H:%M:%S"),
            "params": self.params,
            "source": self.source,
        }

    @classmethod
    def from_row(cls, row: dict) -> "AstroEvent":
        from datetime import timezone
        return cls(
            category=row["category"],
            title=row["title"],
            utc_time=datetime.strptime(row["utc_time"], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc),
            body=row.get("body", ""),
            description=row.get("description", "") or "",
            params=row.get("params", {}),
            source=row.get("source", "") or "",
        )
