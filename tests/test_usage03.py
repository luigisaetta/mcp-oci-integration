"""
Test usage API 02
"""

import json
from consumption_utils import usage_summary_by_service_for_compartment


# --- Esempio d'uso standalone (per test locale) ---
if __name__ == "__main__":
    result = usage_summary_by_service_for_compartment(
        start_day="2025-09-01", end_day_inclusive="2025-09-30", compartment="lsaetta"
    )

    print(json.dumps(result, indent=2))
