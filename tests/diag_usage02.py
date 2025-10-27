"""
OCI Usage API — robust per-service consumption by compartment (self-contained)

Key robustness:
- Service resolution uses union of COST and USAGE service labels in the window.
- If server-side filter returns 0, we drop it and filter client-side (no silent zeroes).
- DAILY + is_aggregate_by_time=True → single total per group across the period.
- Depth <= 7 enforced.

Change the USER INPUTS section at the top as needed.
"""

from __future__ import annotations

import sys
from oci.exceptions import ServiceError

from consumption_utils import fetch_consumption_by_compartment

# -------------------- USER INPUTS --------------------
CONFIG_PROFILE = "DEFAULT"
DAY_START = "2025-10-01"  # inclusive (YYYY-MM-DD)
DAY_END = "2025-10-30"  # inclusive (YYYY-MM-DD)
# service label (case-insensitive, substring ok)
SERVICE = "Database"
QUERY_TYPE = "COST"  # "COST" or "USAGE"
INCLUDE_SUBCOMPARTMENTS = True
MAX_COMPARTMENT_DEPTH = 7
# -------------------------------------------------------------------------

# -------------------------- DEMO / CLI --------------------------
if __name__ == "__main__":
    try:
        result = fetch_consumption_by_compartment(
            day_start=DAY_START,
            day_end=DAY_END,
            service=SERVICE,
            query_type=QUERY_TYPE,
            include_subcompartments=INCLUDE_SUBCOMPARTMENTS,
            max_compartment_depth=MAX_COMPARTMENT_DEPTH,
            config_profile=CONFIG_PROFILE,
            debug=False,  # set to False to return only {"rows": [...]}
        )
        rows = result.get("rows", [])

        if not rows:
            print("No data found even after union discovery and client-side filtering.")
            if "service_candidates" in result:
                print(
                    "Service candidates (first 50):", result.get("service_candidates")
                )
                print("Resolved service:", result.get("resolved_service"))
                print("Query used:", result.get("query_used"))
                print("Depth:", result.get("depth"))
            sys.exit(0)
        else:
            print("**************************")
            print(result)
            print("**************************")
            print("")
            print("")

        print(
            f"Found {len(rows)} rows | query={result.get('query_used','?')} | "
            f"server_side_filter={result.get('filtered_server_side','?')} | depth={result.get('depth','?')}"
        )
        for r in rows[:20]:
            if "computed_amount" in r:
                print(
                    f"{r['service']:<30} | {r['compartment_name']:<24} | {r['compartment_path']:<60} | {r['computed_amount']:.2f} {r.get('currency','')}"
                )
            else:
                print(
                    f"{r['service']:<30} | {r['compartment_name']:<24} | {r['compartment_path']:<60} | {r['computed_quantity']:.2f} {r.get('unit','')}"
                )

        if "service_candidates" in result:
            print("\n[Diagnostics]")
            print(
                "Resolved service:",
                result.get("resolved_service") or "(not uniquely resolved)",
            )
            print("Query used:", result.get("query_used"))
            print(
                "First 50 candidate services:",
                (result.get("service_candidates") or [])[:50],
            )
    except ServiceError as e:
        print(f"[ServiceError] {e.status} {e.code} — {e.message}")
        try:
            print("opc-request-id:", e.headers.get("opc-request-id"))
        except Exception:
            pass
        sys.exit(2)
    except Exception as ex:
        print("ERROR:", ex)
        sys.exit(2)
