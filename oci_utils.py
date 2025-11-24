"""
OCI Utils:
    A collection of utility functions for working with Oracle Cloud Infrastructure (OCI).
"""

from typing import List, Dict, Any
import oci
from oci import retry as oci_retry
from oci.database import DatabaseClient

TAG_KEY = "ref-comp"


def build_retry_strategy():
    """
    Implement a retry strategy for OCI operations.
    """
    return oci_retry.DEFAULT_RETRY_STRATEGY


def get_identity_client() -> tuple[oci.identity.IdentityClient, Dict[str, Any]]:
    """
    Create an IdentityClient from the local OCI config file.
    """
    config = oci.config.from_file()
    client = oci.identity.IdentityClient(config)
    return client, config


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

    identity_client, config = get_identity_client()
    tenancy_id = config["tenancy"]

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


def list_compartments_with_ref_comp(ref_comp_value: str) -> List[Dict[str, str]]:
    """
    Returns a list of compartments with freeform tag 'ref-comp' == ref_comp_value.

    Useful to aggregate costs for compartments tagged with a specific reference
    compartment name.

    Each item is:
    {
        "compartment_id": ...,
        "compartment_name": ...,
    }
    """
    identity_client, config = get_identity_client()
    tenancy_id = config["tenancy"]

    # Get all ACTIVE compartments in the entire tree
    response = oci.pagination.list_call_get_all_results(
        identity_client.list_compartments,
        tenancy_id,
        access_level="ANY",
        compartment_id_in_subtree=True,
        lifecycle_state="ACTIVE",
    )

    results: List[Dict[str, str]] = []

    for comp in response.data:
        # we're looking at freeform tags
        freeform_tags = comp.freeform_tags or {}
        value = freeform_tags.get(TAG_KEY)

        # found the tag with the desired value
        if value == ref_comp_value:
            results.append({"compartment_id": comp.id, "compartment_name": comp.name})

    # result list with items in the form:
    # {"compartment_id": ..., "compartment_name": ...}
    return results
