"""
Identify all compartments missing the 'ref-comp' freeform tag.
"""

import oci
from typing import Dict, List, Any

from oci_utils import get_identity_client

TAG_KEY = "ref-comp"


def list_compartments_missing_ref_comp() -> List[Dict[str, str]]:
    """
    Returns a list of compartments that *do not* have the 'ref-comp' freeform tag.

    Each item in the result is:
    {
        "compartment_id": ...,
        "compartment_name": ...,
        "path_info": (optional, if you want to enrich later)
    }
    """
    identity_client, config = get_identity_client()
    tenancy_id = config["tenancy"]

    # Get ALL compartments across the entire subtree
    response = oci.pagination.list_call_get_all_results(
        identity_client.list_compartments,
        tenancy_id,
        access_level="ANY",
        compartment_id_in_subtree=True,
        lifecycle_state="ACTIVE",
    )

    results = []

    for comp in response.data:
        freeform_tags = comp.freeform_tags or {}

        # Keep only those WITHOUT the tag
        if TAG_KEY not in freeform_tags:
            results.append(
                {
                    "compartment_id": comp.id,
                    "compartment_name": comp.name,
                }
            )

    return results


if __name__ == "__main__":
    missing = list_compartments_missing_ref_comp()

    if not missing:
        print("All compartments have the 'ref-comp' tag.")
    else:
        print(f"Found {len(missing)} compartments missing 'ref-comp':")
        for comp in missing:
            print("------")
            print("Name:", comp["compartment_name"])
            # print("OCID:", comp["compartment_id"])
