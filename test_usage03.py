"""
Test usage API 02
"""

import json
from consumption_utils import (
    usage_summary_by_service_structured,
    usage_summary_by_compartment_structured,
    usage_of_service_by_compartment,
)


# --- Esempio d'uso standalone (per test locale) ---
if __name__ == "__main__":
    result = usage_of_service_by_compartment(
        start_day="2025-09-01",
        end_day_inclusive="2025-09-30",
        service_name="OCI Database Service with PostgreSQL",
        query_type="COST",
        compartment_depth=1,
    )

    print(json.dumps(result, indent=2))
