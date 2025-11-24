"""
Test the code to get compartments with a specific freeform tag 'ref-comp'.
"""

from oci_utils import list_compartments_with_ref_comp

if __name__ == "__main__":
    REF_COMP = "omasalem"
    comps = list_compartments_with_ref_comp(REF_COMP)

    if not comps:
        print(f"No compartments found with ref-comp = '{REF_COMP}'.")
    else:
        print(f"Compartments with ref-comp = '{REF_COMP}':")
        for c in comps:
            print("------")
            print("Name:", c["compartment_name"])
            print("OCID:", c["compartment_id"])
