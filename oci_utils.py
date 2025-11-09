"""
OCI Utils:
    A collection of utility functions for working with Oracle Cloud Infrastructure (OCI).
"""

from typing import List
import oci
from oci import retry as oci_retry
from oci.database import DatabaseClient


def build_retry_strategy():
    """
    Implement a retry strategy for OCI operations.
    """
    return oci_retry.DEFAULT_RETRY_STRATEGY


def list_adbs_in_compartment(compartment_id: str):
    """
    List all Autonomous Databases in a given compartment.
    """
    retry = build_retry_strategy()

    config = oci.config.from_file()
    db_client = DatabaseClient(config)

    adbs_raw = oci.pagination.list_call_get_all_results(
        db_client.list_autonomous_databases,
        compartment_id=compartment_id,
        retry_strategy=retry,
    ).data

    adbs = []

    for adb in adbs_raw:
        adbs.append(_adb_row(adb))

    return adbs


def list_adbs_in_compartment_list(compartment_list: list):
    """
    list all ADBS in a list of compartments.
    Compartments are identified by name
    """
    return_list = []

    for comp_name in compartment_list:
        comp_id = get_compartment_id_by_name(comp_name)

        if comp_id is not None:
            list_adbs = list_adbs_in_compartment(comp_id)

            result = {"compartment": comp_name, "autonomous_databases": list_adbs}
            return_list.append(result)

    return {"results": return_list}


def _adb_row(adb) -> dict:
    """
    Extract the data regarding adb into a dictionary.
    """
    return {
        "display_name": getattr(adb, "display_name", ""),
        "db_name": getattr(adb, "db_name", ""),
        "lifecycle_state": getattr(adb, "lifecycle_state", ""),
        "workload": getattr(adb, "db_workload", ""),
        "cpu_core_count": getattr(adb, "cpu_core_count", None),
        "data_storage_tbs": getattr(adb, "data_storage_size_in_tbs", None),
        "is_free_tier": getattr(adb, "is_free_tier", None),
        "license_model": getattr(adb, "license_model", ""),
    }


def get_compartment_id_by_name(name: str) -> str | None:
    """
    Return the OCID of the compartment (or tenancy) with the given name.

    - Searches recursively across all ACTIVE compartments in the tenancy.
    - Matches case-insensitively.
    - Returns None if not found.

    Example:
        cid = get_compartment_id_by_name(identity_client, tenancy_id, "MyCompartment")
        if cid:
            print("OCID:", cid)
        else:
            print("Not found")
    """
    retry = build_retry_strategy()

    config = oci.config.from_file()
    tenancy_id = config["tenancy"]
    identity_client = oci.identity.IdentityClient(config)

    # Root tenancy
    tenancy_details = identity_client.get_tenancy(tenancy_id, retry_strategy=retry).data
    if tenancy_details.name.lower() == name.lower():
        return tenancy_id

    # Get all sub-compartments
    compartments = oci.pagination.list_call_get_all_results(
        identity_client.list_compartments,
        tenancy_id,
        compartment_id_in_subtree=True,
        access_level="ACCESSIBLE",
        lifecycle_state="ACTIVE",
        retry_strategy=retry,
    ).data

    for c in compartments:
        if c.name.lower() == name.lower() and c.lifecycle_state == "ACTIVE":
            return c.id

    return None


def list_all_compartments() -> List[oci.identity.models.Compartment]:
    """
    Return ACTIVE compartments (including sub-compartments) + a synthetic root entry for the tenancy.
    """

    retry = build_retry_strategy()

    config = oci.config.from_file()
    tenancy_id = config["tenancy"]
    identity_client = oci.identity.IdentityClient(config)

    # include root "tenancy" as a pseudo-compartment
    tenancy_details = identity_client.get_tenancy(tenancy_id, retry_strategy=retry).data
    root = oci.identity.models.Compartment(
        id=tenancy_id,
        name=tenancy_details.name,
        description="Tenancy Root",
        lifecycle_state="ACTIVE",
        compartment_id=None,  # no parent
    )

    # Pull sub-tree
    compartments = oci.pagination.list_call_get_all_results(
        identity_client.list_compartments,
        tenancy_id,
        compartment_id_in_subtree=True,
        access_level="ACCESSIBLE",
        lifecycle_state="ACTIVE",
        retry_strategy=retry,
    ).data

    # Keep only ACTIVE
    compartments = [c for c in compartments if c.lifecycle_state == "ACTIVE"]
    # Add root at the beginning
    return [root] + compartments
