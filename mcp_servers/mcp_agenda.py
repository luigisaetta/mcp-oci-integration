"""
Agenda MCP server implementation.
"""

from typing import List, Dict, Any
from mcp_utils import create_server, run_server
from agenda_utils import add_event, get_events

mcp = create_server("Agenda MCP")


@mcp.tool()
def list_events(start_date: str, end_date: str) -> Dict[str, Any]:
    """
    List all events in the agenda that overlap with the given interval.

    Parameters
    ----------
    start_date : str
        Start of the desired interval.
        Accepted formats:
        - 'YYYY-MM-DDTHH:MM:SS'
        - 'YYYY-MM-DD HH:MM'
        - 'YYYY-MM-DD'
    end_date : str
        End of the desired interval.
        Same accepted formats as start_date.

    Returns
    -------
    dict
        JSON object with a single key "events":

        {
          "events": [
            {
              "title": str,
              "start": str,  # ISO 8601
              "end": str     # ISO 8601
            },
            ...
          ]
        }
    """
    events = get_events(start_date, end_date)

    return {"events": events}


@mcp.tool()
def create_event(title: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Create a new event in the agenda and report any scheduling conflicts.

    Parameters
    ----------
    title : str
        Short human-readable title of the event.
    start_date : str
        Start of the event.
        Accepted formats:
        - 'YYYY-MM-DDTHH:MM:SS'
        - 'YYYY-MM-DD HH:MM'
        - 'YYYY-MM-DD'
    end_date : str
        End of the event.
        Must be strictly after start_date.
        Same accepted formats as start_date.

    Returns
    -------
    dict
        JSON object describing the created event and any conflicts:

        {
          "title": str,
          "start": str,         # ISO 8601
          "end": str,           # ISO 8601
          "has_conflict": bool,
          "conflicts": [
            {
              "title": str,
              "start": str,     # ISO 8601
              "end": str        # ISO 8601
            },
            ...
          ]
        }

    Notes
    -----
    - The event is always created, even if there are conflicts.
    - If dates are invalid or end_date <= start_date, a ValueError is raised.
    """
    return add_event(title, start_date, end_date)


if __name__ == "__main__":
    run_server(mcp)
