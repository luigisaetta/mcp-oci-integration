"""
Agenda utils
Provides in-memory storage and retrieval of calendar events.
"""

from datetime import datetime
from typing import List, Dict, Any

# Internal in-memory event store
# Each event is stored as: {"title": str, "start": datetime, "end": datetime}
EVENTS: List[Dict[str, Any]] = []


def parse_dt(value: str) -> datetime:
    """
    Parse a datetime in ISO8601 or common date formats.
    Accepted formats:
      - YYYY-MM-DDTHH:MM:SS
      - YYYY-MM-DD HH:MM
      - YYYY-MM-DD
    """
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass

    raise ValueError(f"Invalid datetime format: {value}")


def _overlaps(
    start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime
) -> bool:
    """
    Return True if two intervals [start_a, end_a] and [start_b, end_b] overlap.
    """
    # strict-ish overlap (you can tweak as you prefer)
    return end_a > start_b and end_b > start_a


def add_event(title: str, start: str, end: str) -> Dict[str, Any]:
    """
    Add a new event to the in-memory list.

    Returns a JSON-safe dict:
        {
            "title": str,
            "start": str (ISO 8601),
            "end": str (ISO 8601),
            "has_conflict": bool,
            "conflicts": [
                {"title": str, "start": str (ISO 8601), "end": str (ISO 8601)},
                ...
            ]
        }
    """
    start_dt = parse_dt(start)
    end_dt = parse_dt(end)

    if end_dt <= start_dt:
        raise ValueError("end must be strictly after start")

    # Identify conflicts BEFORE adding the new one
    conflicts: List[Dict[str, Any]] = []
    for ev in EVENTS:
        if _overlaps(ev["start"], ev["end"], start_dt, end_dt):
            conflicts.append(
                {
                    "title": ev["title"],
                    "start": ev["start"].isoformat(),
                    "end": ev["end"].isoformat(),
                }
            )

    # Store internal representation (with datetime objects)
    EVENTS.append(
        {
            "title": title,
            "start": start_dt,
            "end": end_dt,
        }
    )

    # Return JSON-safe data
    return {
        "title": title,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "has_conflict": len(conflicts) > 0,
        "conflicts": conflicts,
    }


def get_events(start: str, end: str) -> List[Dict[str, Any]]:
    """
    Return all events overlapping with the given interval.

    The result is JSON-safe:
      [{"title": ..., "start": ISO8601, "end": ISO8601}, ...]
    """
    start_dt = parse_dt(start)
    end_dt = parse_dt(end)

    results: List[Dict[str, Any]] = []
    for ev in EVENTS:
        if _overlaps(ev["start"], ev["end"], start_dt, end_dt):
            results.append(
                {
                    "title": ev["title"],
                    "start": ev["start"].isoformat(),
                    "end": ev["end"].isoformat(),
                }
            )

    return results
