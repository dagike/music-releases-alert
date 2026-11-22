from __future__ import annotations

from datetime import datetime, time, timedelta


def parse_schedule(text: str) -> list[time]:
    """Parse "00:15,06:00" into a sorted list of times."""
    times = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            hour, minute = part.split(":")
            times.add(time(int(hour), int(minute)))
        except ValueError:
            raise ValueError(f"Bad time '{part}' in SCHEDULE. Use HH:MM.") from None
    if not times:
        raise ValueError("SCHEDULE has no times.")
    return sorted(times)


def next_run(after: datetime, schedule: list[time]) -> datetime:
    """Return the first scheduled moment that is later than `after`."""
    for day in range(3):
        date = after.date() + timedelta(days=day)
        for t in schedule:
            candidate = datetime.combine(date, t)
            if candidate > after:
                return candidate
    raise RuntimeError("unreachable: schedule is not empty")
