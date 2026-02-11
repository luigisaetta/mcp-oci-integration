"""
Baseline contract tests for mcp_servers/mcp_consumption.py.

These tests mock downstream utility calls so they stay deterministic
and do not require OCI/network access.

run from the repo root as:
PYTHONPATH=. python3 -m pytest -q tests/test_mcp_consumption_tools.py
"""

import mcp_servers.mcp_consumption as mod


def _invoke_tool(tool_obj, *args, **kwargs):
    """
    Call a tool regardless of whether FastMCP wrapped it as FunctionTool
    or left it as a plain function.
    """
    if callable(tool_obj):
        return tool_obj(*args, **kwargs)

    # FastMCP FunctionTool usually exposes the original callable as .fn
    for attr in ("fn", "func", "_fn"):
        candidate = getattr(tool_obj, attr, None)
        if callable(candidate):
            return candidate(*args, **kwargs)

    raise TypeError(f"Unsupported tool object: {type(tool_obj)!r}")


def test_usage_summary_by_service_success(monkeypatch):
    expected = {"items": [{"service": "Compute", "amount": 10.5}]}
    monkeypatch.setattr(mod, "usage_summary_by_service_structured", lambda s, e: expected)

    out = _invoke_tool(mod.usage_summary_by_service, "2025-01-01", "2025-01-31")
    assert out == expected


def test_usage_summary_by_service_error(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "usage_summary_by_service_structured", _raise)

    out = _invoke_tool(mod.usage_summary_by_service, "2025-01-01", "2025-01-31")
    assert "error" in out
    assert "boom" in out["error"]


def test_usage_summary_by_compartment_success(monkeypatch):
    expected = {"items": [{"compartmentName": "ABC", "amount": 9.0}]}
    monkeypatch.setattr(
        mod, "usage_summary_by_compartment_structured", lambda s, e: expected
    )

    out = _invoke_tool(mod.usage_summary_by_compartment, "2025-01-01", "2025-01-31")
    assert out == expected


def test_usage_summary_by_compartment_error(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("bad request")

    monkeypatch.setattr(mod, "usage_summary_by_compartment_structured", _raise)

    out = _invoke_tool(mod.usage_summary_by_compartment, "2025-01-01", "2025-01-31")
    assert "error" in out
    assert "bad request" in out["error"]


def test_usage_breakdown_for_service_by_compartment_success(monkeypatch):
    expected = {"rows": [{"service": "Storage", "computed_amount": 5.2}]}
    monkeypatch.setattr(
        mod, "fetch_consumption_by_compartment", lambda s, e, svc: expected
    )

    out = _invoke_tool(
        mod.usage_breakdown_for_service_by_compartment,
        "2025-01-01", "2025-01-31", "Storage"
    )
    assert out == expected


def test_usage_breakdown_for_service_by_compartment_error(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("service not found")

    monkeypatch.setattr(mod, "fetch_consumption_by_compartment", _raise)

    out = _invoke_tool(
        mod.usage_breakdown_for_service_by_compartment,
        "2025-01-01", "2025-01-31", "Storage"
    )
    assert "error" in out
    assert "service not found" in out["error"]


def test_usage_breakdown_for_compartment_by_service_success(monkeypatch):
    expected = {"items": [{"service": "Compute", "amount": 15.1}]}
    monkeypatch.setattr(
        mod, "usage_summary_by_service_for_compartment", lambda s, e, c: expected
    )

    out = _invoke_tool(
        mod.usage_breakdown_for_compartment_by_service,
        "2025-01-01", "2025-01-31", "MyCompartment"
    )
    assert out == expected


def test_usage_breakdown_for_compartment_by_service_error(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("compartment not found")

    monkeypatch.setattr(mod, "usage_summary_by_service_for_compartment", _raise)

    out = _invoke_tool(
        mod.usage_breakdown_for_compartment_by_service,
        "2025-01-01", "2025-01-31", "MissingCompartment"
    )
    assert "error" in out
    assert "compartment not found" in out["error"]


def test_list_adb_for_compartment_success(monkeypatch):
    monkeypatch.setattr(mod, "get_compartment_id_by_name", lambda name: "ocid1.compartment.x")
    monkeypatch.setattr(
        mod,
        "list_adbs_in_compartment",
        lambda cid: [{"display_name": "ADB1", "id": "ocid1.autonomousdatabase.x"}],
    )

    out = _invoke_tool(mod.list_adb_for_compartment, "MyCompartment")
    assert "autonomous_databases" in out
    assert len(out["autonomous_databases"]) == 1


def test_list_adb_for_compartment_not_found(monkeypatch):
    monkeypatch.setattr(mod, "get_compartment_id_by_name", lambda name: None)

    out = _invoke_tool(mod.list_adb_for_compartment, "MissingCompartment")
    assert "error" in out
    assert "not found" in out["error"]


def test_list_adb_for_compartment_error(monkeypatch):
    monkeypatch.setattr(mod, "get_compartment_id_by_name", lambda name: "ocid1.compartment.x")

    def _raise(*_args, **_kwargs):
        raise RuntimeError("oci api error")

    monkeypatch.setattr(mod, "list_adbs_in_compartment", _raise)

    out = _invoke_tool(mod.list_adb_for_compartment, "MyCompartment")
    assert "error" in out
    assert "oci api error" in out["error"]


def test_list_adb_for_compartments_list_success(monkeypatch):
    expected = {"results": [{"compartment": "A", "autonomous_databases": []}]}
    monkeypatch.setattr(mod, "list_adbs_in_compartment_list", lambda c: expected)

    out = _invoke_tool(mod.list_adb_for_compartments_list, ["A"])
    assert out == expected


def test_list_adb_for_compartments_list_error(monkeypatch):
    def _raise(*_args, **_kwargs):
        raise RuntimeError("bad input")

    monkeypatch.setattr(mod, "list_adbs_in_compartment_list", _raise)

    out = _invoke_tool(mod.list_adb_for_compartments_list, ["A"])
    assert "error" in out
    assert "bad input" in out["error"]


def test_usage_summary_by_service_invalid_date():
    out = _invoke_tool(mod.usage_summary_by_service, "2025/01/01", "2025-01-31")
    assert "error" in out
    assert "YYYY-MM-DD" in out["error"]


def test_usage_summary_by_compartment_reversed_dates():
    out = _invoke_tool(mod.usage_summary_by_compartment, "2025-02-01", "2025-01-31")
    assert "error" in out
    assert "start_date must be <= end_date" in out["error"]


def test_usage_breakdown_for_service_by_compartment_empty_service_name():
    out = _invoke_tool(
        mod.usage_breakdown_for_service_by_compartment,
        "2025-01-01",
        "2025-01-31",
        "   ",
    )
    assert "error" in out
    assert "service_name must be a non-empty string" in out["error"]


def test_usage_breakdown_for_compartment_by_service_empty_compartment_name():
    out = _invoke_tool(
        mod.usage_breakdown_for_compartment_by_service,
        "2025-01-01",
        "2025-01-31",
        "",
    )
    assert "error" in out
    assert "compartment_name must be a non-empty string" in out["error"]


def test_list_adb_for_compartment_empty_name():
    out = _invoke_tool(mod.list_adb_for_compartment, " ")
    assert "error" in out
    assert "compartment_name must be a non-empty string" in out["error"]


def test_list_adb_for_compartments_list_empty_list():
    out = _invoke_tool(mod.list_adb_for_compartments_list, [])
    assert "error" in out
    assert "non-empty list" in out["error"]


def test_list_adb_for_compartments_list_invalid_item_type():
    out = _invoke_tool(mod.list_adb_for_compartments_list, ["A", 42])
    assert "error" in out
    assert "contain only non-empty strings" in out["error"]
