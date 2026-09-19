from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from skyfield.api import load
from skyfield.framelib import ecliptic_frame

TERMS = [
    "春分", "清明", "谷雨", "立夏", "小满", "芒种", "夏至", "小暑",
    "大暑", "立秋", "处暑", "白露", "秋分", "寒露", "霜降", "立冬",
    "小雪", "大雪", "冬至", "小寒", "大寒", "立春", "雨水", "惊蛰",
]


@dataclass
class SolarSeason:
    longitude: float
    current_term: str
    next_term: str
    next_term_at: str
    progress: float
    season_sin: float
    season_cos: float


class SolarCalculator:
    def __init__(self, ephemeris_path: str, timezone_name: str):
        if not Path(ephemeris_path).exists():
            raise FileNotFoundError(ephemeris_path)
        self.ts = load.timescale()
        self.eph = load(ephemeris_path)
        self.earth, self.sun = self.eph["earth"], self.eph["sun"]
        self.zone = ZoneInfo(timezone_name)

    def longitude(self, when: datetime) -> float:
        when = when.astimezone(timezone.utc)
        t = self.ts.from_datetime(when)
        _, lon, _ = self.earth.at(t).observe(self.sun).apparent().frame_latlon(ecliptic_frame)
        return lon.degrees % 360

    def _crossing(self, start: datetime, target: float) -> datetime:
        left = start
        for _ in range(17 * 24):
            right = left + timedelta(hours=1)
            a = (self.longitude(left) - target) % 360
            b = (self.longitude(right) - target) % 360
            if a > 350 and b < 10:
                for _ in range(20):
                    mid = left + (right - left) / 2
                    m = (self.longitude(mid) - target) % 360
                    if m > 180:
                        left = mid
                    else:
                        right = mid
                return right
            left = right
        raise RuntimeError("solar term crossing not found")

    def season(self, when: datetime) -> SolarSeason:
        lon = self.longitude(when)
        index = int(lon // 15)
        progress = (lon % 15) / 15
        next_index = (index + 1) % 24
        crossing = self._crossing(when, next_index * 15)
        radians = math.radians(lon)
        return SolarSeason(
            longitude=round(lon, 6),
            current_term=TERMS[index],
            next_term=TERMS[next_index],
            next_term_at=crossing.astimezone(self.zone).isoformat(),
            progress=round(progress, 6),
            season_sin=round(math.sin(radians), 6),
            season_cos=round(math.cos(radians), 6),
        )
