"""
OCI Usage API: zero-results diagnosis (single-file, self-running)

What it does:
- Checks auth/tenant/region
- Normalizes date window (inclusive end)
- Lists services with activity in the window
- Runs unfiltered grouped queries (COST and USAGE)
- Optionally inspects one target service to see if naming/filter/query_type is the culprit
"""

from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import sys
import oci
from oci.exceptions import ServiceError
from oci.usage_api import UsageapiClient
from oci.usage_api.models import RequestSummarizedUsagesDetails

# ===================== USER INPUTS =====================
CONFIG_PROFILE = (
    "DEFAULT"  # ~/.oci/config profile; set to None to try resource principals
)
DAY_START = "2025-09-01"  # inclusive (YYYY-MM-DD)
DAY_END = "2025-09-30"  # inclusive (YYYY-MM-DD)
TARGET_SERVICE = "Compute"  # set to None to skip service-specific tests
INCLUDE_SUBCOMPARTMENTS = True  # False -> root level only
MAX_COMPARTMENT_DEPTH = 7  # must be 1..7
# =======================================================


def _to_utc_day_start(d: date | datetime | str) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    if isinstance(d, datetime):
        d = d.date()
    dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
    return (
        dt.replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _to_utc_day_end_exclusive(d: date | datetime | str) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    if isinstance(d, datetime):
        d = d.date()
    next_day = d + timedelta(days=1)
    dt = datetime(next_day.year, next_day.month, next_day.day, tzinfo=timezone.utc)
    return (
        dt.replace(hour=0, minute=0, second=0, microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _effective_depth(include_sub: bool, max_depth: int) -> int:
    if not include_sub:
        return 1
    return max(1, min(int(max_depth), 7))


def _make_client() -> tuple[UsageapiClient, Dict[str, Any]]:
    cfg: Optional[Dict[str, Any]] = None
    try:
        if CONFIG_PROFILE is not None:
            cfg = oci.config.from_file(profile_name=CONFIG_PROFILE)
    except Exception:
        cfg = None

    if cfg is not None:
        client = UsageapiClient(cfg)
        return client, cfg

    # Fallback: resource principals
    signer = oci.auth.signers.get_resource_principals_signer()
    cfg = {"region": signer.region, "tenancy": signer.tenancy_id}
    client = UsageapiClient(cfg, signer=signer)
    return client, cfg


def _list_services(
    client: UsageapiClient, tenant_id: str, t_start: str, t_end_excl: str, depth: int
) -> List[str]:
    details = RequestSummarizedUsagesDetails(
        tenant_id=tenant_id,
        granularity=RequestSummarizedUsagesDetails.GRANULARITY_DAILY,  # TOTAL is not supported
        query_type=RequestSummarizedUsagesDetails.QUERY_TYPE_COST,
        is_aggregate_by_time=True,
        time_usage_started=t_start,
        time_usage_ended=t_end_excl,
        group_by=["service"],
        compartment_depth=depth,
    )
    resp = client.request_summarized_usages(details)
    services = set()
    for it in getattr(resp.data, "items", []) or []:
        s = getattr(it, "service", None)
        if s:
            services.add(s)
    return sorted(services)


def _probe(
    client: UsageapiClient,
    tenant_id: str,
    t_start: str,
    t_end_excl: str,
    depth: int,
    query_type: str,
):
    details = RequestSummarizedUsagesDetails(
        tenant_id=tenant_id,
        granularity=RequestSummarizedUsagesDetails.GRANULARITY_DAILY,
        query_type=query_type,
        is_aggregate_by_time=True,
        time_usage_started=t_start,
        time_usage_ended=t_end_excl,
        group_by=["compartmentPath", "compartmentName", "compartmentId", "service"],
        compartment_depth=depth,
    )
    resp = client.request_summarized_usages(details)
    items = getattr(resp.data, "items", []) or []
    return items


def _show_top(items: List[Any], query_type: str, limit: int = 15):
    # Sort by amount/quantity desc and print a few rows
    def amt(x):
        return (
            getattr(x, "computed_amount", 0.0)
            if query_type == "COST"
            else getattr(x, "computed_quantity", 0.0)
        )

    items_sorted = sorted(items, key=amt, reverse=True)
    print(f"Top {min(limit,len(items_sorted))} rows ({query_type}):")
    for it in items_sorted[:limit]:
        path = getattr(it, "compartment_path", "")
        name = getattr(it, "compartment_name", "")
        svc = getattr(it, "service", "")
        if query_type == "COST":
            val = getattr(it, "computed_amount", 0.0)
            cur = getattr(it, "currency", "")
            print(f"  {svc:25} | {name:25} | {path:40} | {val:.2f} {cur}")
        else:
            val = getattr(it, "computed_quantity", 0.0)
            unit = getattr(it, "unit", "")
            print(f"  {svc:25} | {name:25} | {path:40} | {val:.2f} {unit}")
    print()


def _filter_items_by_service(items: List[Any], service_key: str) -> List[Any]:
    exact = [
        x
        for x in items
        if getattr(x, "service", "").casefold() == service_key.casefold()
    ]
    if exact:
        return exact
    # fallback: substring match
    return [
        x
        for x in items
        if service_key.casefold() in getattr(x, "service", "").casefold()
    ]


def main():
    if not 1 <= MAX_COMPARTMENT_DEPTH <= 7:
        print("ERROR: MAX_COMPARTMENT_DEPTH must be 1..7")
        sys.exit(2)

    t_start = _to_utc_day_start(DAY_START)
    t_end_excl = _to_utc_day_end_exclusive(DAY_END)
    depth = _effective_depth(INCLUDE_SUBCOMPARTMENTS, MAX_COMPARTMENT_DEPTH)

    try:
        client, cfg = _make_client()
        tenant_id = cfg.get("tenancy")
        region = cfg.get("region")
        print(f"[Auth] tenancy={tenant_id} region={region}")
        print(
            f"[Window] {DAY_START}..{DAY_END} (inclusive) => {t_start} .. {t_end_excl} [exclusive]"
        )
        print(f"[Depth] include_sub={INCLUDE_SUBCOMPARTMENTS} effective_depth={depth}")
        print()

        # 1) List services in window (based on COST)
        services = _list_services(client, tenant_id, t_start, t_end_excl, depth)
        print(f"Services with COST data in window ({len(services)}):")
        for s in services[:50]:
            print("  -", s)
        if not services:
            print(
                "No services found in this window. Try widening the dates or check billing availability."
            )
            return
        print()

        # 2) Unfiltered probes: COST then USAGE
        for qt in ("COST", "USAGE"):
            try:
                items = _probe(client, tenant_id, t_start, t_end_excl, depth, qt)
                print(f"[Probe {qt}] rows={len(items)}")
                if items:
                    _show_top(items, qt)
                else:
                    print(
                        f"No rows for {qt}. (Possible: credits/no cost, or no usage units for services in range)\n"
                    )
            except ServiceError as e:
                print(
                    f"[Probe {qt}] ServiceError {e.status} {e.code} (opc-request-id={e.headers.get('opc-request-id') if hasattr(e,'headers') else 'n/a'})"
                )
                print(e)
                print()

        # 3) If user specified a target service, try to match it and show rows
        if TARGET_SERVICE:
            # prefer an exact match from services list, otherwise keep user input
            svc_exact = next(
                (s for s in services if s.casefold() == TARGET_SERVICE.casefold()), None
            )
            svc_key = svc_exact or TARGET_SERVICE
            print(f"[Target Service] requested='{TARGET_SERVICE}' resolved='{svc_key}'")
            # Use the COST/USAGE probe results we already have (or fetch COST if needed)
            items_cost = _probe(client, tenant_id, t_start, t_end_excl, depth, "COST")
            items_usage = _probe(client, tenant_id, t_start, t_end_excl, depth, "USAGE")

            sel_cost = _filter_items_by_service(items_cost, svc_key)
            sel_usage = _filter_items_by_service(items_usage, svc_key)

            print(f"  COST rows for '{svc_key}': {len(sel_cost)}")
            if sel_cost:
                _show_top(sel_cost, "COST", limit=10)
            else:
                print("  (No COST rows for this service in the window.)\n")

            print(f"  USAGE rows for '{svc_key}': {len(sel_usage)}")
            if sel_usage:
                _show_top(sel_usage, "USAGE", limit=10)
            else:
                print("  (No USAGE rows for this service in the window.)\n")

            if not sel_cost and not sel_usage:
                print("Diagnosis:")
                print(
                    " - The service name likely doesn't match billing labels in this window,"
                )
                print(
                    "   or there is genuinely no activity for this service/date range."
                )
                print(
                    " - Copy a name exactly from the 'Services with COST data' list above,"
                )
                print("   or widen the date range.")
                print(
                    " - If COST is always 0 but USAGE has rows, you may be on credits/reserved pricing."
                )
                print()

    except ServiceError as e:
        print(f"[FATAL] ServiceError {e.status} {e.code}")
        print(f"Message: {e.message}")
        try:
            print(f"opc-request-id: {e.headers.get('opc-request-id')}")
        except Exception:
            pass
        print("Tip: enable OCI SDK debug logging to see the request payload.")
        sys.exit(1)


if __name__ == "__main__":
    main()
