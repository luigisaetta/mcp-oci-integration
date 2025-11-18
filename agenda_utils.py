"""
Agenda utils
Provides in-memory storage and retrieval of calendar events.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional

# Internal in-memory event store
# Each event is stored as:
#   {"id": int, "title": str, "start": datetime, "end": datetime}
EVENTS: List[Dict[str, Any]] = []

# Simple incremental ID generator for events
NEXT_ID: int = 1


def parse_dt(value: str) -> datetime:
    """
    Parse a datetime in ISO8601 or common date formats.

    Accepted formats:
      - YYYY-MM-DDTHH:MM:SS
      - YYYY-MM-DD HH:MM
      - YYYY-MM-DD

    Raises:
        ValueError: if none of the formats match.
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

    Overlap condition is strict on time, i.e. if one event ends exactly when
    another starts, they do NOT overlap.
    """
    return end_a > start_b and end_b > start_a


def _serialize_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert an internal event (with datetime) to a JSON-safe dict.
    """
    return {
        "id": ev["id"],
        "title": ev["title"],
        "start": ev["start"].isoformat(),
        "end": ev["end"].isoformat(),
    }


def add_event(title: str, start: str, end: str) -> Dict[str, Any]:
    """
    Add a new event to the in-memory list.

    Parameters
    ----------
    title : str
        Title of the event.
    start : str
        Start datetime (string). Accepted formats:
        - YYYY-MM-DDTHH:MM:SS
        - YYYY-MM-DD HH:MM
        - YYYY-MM-DD
    end : str
        End datetime (string). Same formats as `start`.
        Must be strictly after `start`.

    Returns
    -------
    dict
        JSON-safe description of the created event and conflicts:

        {
            "id": int,
            "title": str,
            "start": str,         # ISO 8601
            "end": str,           # ISO 8601
            "has_conflict": bool,
            "conflicts": [
                {
                    "id": int,
                    "title": str,
                    "start": str, # ISO 8601
                    "end": str    # ISO 8601
                },
                ...
            ]
        }

    Notes
    -----
    - The event is always created, even if there are conflicts.
    - Raises ValueError if dates are invalid or end <= start.
    """
    global NEXT_ID

    start_dt = parse_dt(start)
    end_dt = parse_dt(end)

    if end_dt <= start_dt:
        raise ValueError("end must be strictly after start")

    # Identify conflicts BEFORE adding the new one
    conflicts: List[Dict[str, Any]] = []
    for ev in EVENTS:
        if _overlaps(ev["start"], ev["end"], start_dt, end_dt):
            conflicts.append(_serialize_event(ev))

    # Store internal representation (with datetime objects and ID)
    event_id = NEXT_ID
    NEXT_ID += 1

    new_event = {
        "id": event_id,
        "title": title,
        "start": start_dt,
        "end": end_dt,
    }
    EVENTS.append(new_event)

    # Return JSON-safe data including conflicts
    serialized = _serialize_event(new_event)
    serialized.update(
        {
            "has_conflict": len(conflicts) > 0,
            "conflicts": conflicts,
        }
    )
    return serialized


def get_events(start: str, end: str) -> List[Dict[str, Any]]:
    """
    Return all events overlapping with the given interval.

    Parameters
    ----------
    start : str
        Start of the query interval (string).
        Accepted formats:
        - YYYY-MM-DDTHH:MM:SS
        - YYYY-MM-DD HH:MM
        - YYYY-MM-DD
    end : str
        End of the query interval (string).
        Same formats as `start`.

    Returns
    -------
    list of dict
        JSON-safe events:

        [
            {
                "id": int,
                "title": str,
                "start": str,   # ISO 8601
                "end": str      # ISO 8601
            },
            ...
        ]
    """
    start_dt = parse_dt(start)
    end_dt = parse_dt(end)

    results: List[Dict[str, Any]] = []
    for ev in EVENTS:
        if _overlaps(ev["start"], ev["end"], start_dt, end_dt):
            results.append(_serialize_event(ev))

    return results


def delete_event(event_id: int) -> Dict[str, Any]:
    """
    Delete a single event by its unique ID.

    Parameters
    ----------
    event_id : int
        The unique identifier of the event, as returned by add_event or get_events.

    Returns
    -------
    dict
        JSON-safe result object:

        - deleted : bool
            True if an event was removed, False otherwise.
        - event : dict or None
            If deleted == True, the JSON-safe representation of the deleted event:
            {
                "id": int,
                "title": str,
                "start": str,  # ISO 8601
                "end": str     # ISO 8601
            }
            If deleted == False, this will be None.
        - message : str
            Human-readable summary.
    """
    index_to_remove: Optional[int] = None
    for idx, ev in enumerate(EVENTS):
        if ev["id"] == event_id:
            index_to_remove = idx
            break

    if index_to_remove is None:
        return {
            "deleted": False,
            "event": None,
            "message": f"Event with id {event_id} not found.",
        }

    ev = EVENTS.pop(index_to_remove)
    return {
        "deleted": True,
        "event": _serialize_event(ev),
        "message": f"Event with id {event_id} deleted.",
    }
