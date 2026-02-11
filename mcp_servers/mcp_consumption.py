"""
File name: mcp_consumption.py
Author: Luigi Saetta
Date last modified: 2026-02-11
Python Version: 3.11

Description:
    This module implements an MCP (Model Context Protocol) server for querying OCI (Oracle Cloud Infrastructure)
    usage and consumption data. It provides tools for generating usage summaries by service or compartment,
    detailed breakdowns, and listing Autonomous Databases (ADBs) in specified compartments.

Usage:
    Import this module to use its tools or run it as a standalone MCP server.
    Example:
        from mcp_servers.mcp_consumption import usage_summary_by_service

        results = usage_summary_by_service("2025-01-01", "2025-03-31")
        # Or run the server: python mcp_consumption.py

License:
    This code is released under the MIT License.

Notes:
    This is part of the MCP-OCI integration framework and relies on utilities from consumption_utils and oci_utils.
    Tools are designed for integration with MCP agents and handle errors with structured dictionary outputs.

Warnings:
    This module is in development and may change in future versions. Ensure date ranges do not exceed 93 days
    to avoid API errors, and handle potential exceptions in production use.
"""

from typing import Any, Dict, List
from datetime import date

# here are functions calling OCI API
from consumption_utils import (
    usage_summary_by_service_structured,
    usage_summary_by_compartment_structured,
    fetch_consumption_by_compartment,
    usage_summary_by_service_for_compartment,
)
from oci_utils import (
    list_adbs_in_compartment,
    get_compartment_id_by_name,
    list_adbs_in_compartment_list,
)
from mcp_utils import create_server, run_server
from utils import get_console_logger

from config import DEBUG

logger = get_console_logger()

mcp = create_server("OCI Consumption MCP server")


def _validate_iso_date(value: str, field_name: str) -> None:
    """
    Validate that a value is a non-empty ISO date string (YYYY-MM-DD).
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string in YYYY-MM-DD format")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be in YYYY-MM-DD format") from exc


def _validate_date_range(start_date: str, end_date: str) -> None:
    """
    Validate both dates and ensure start_date is not after end_date.
    """
    _validate_iso_date(start_date, "start_date")
    _validate_iso_date(end_date, "end_date")
    if date.fromisoformat(start_date) > date.fromisoformat(end_date):
        raise ValueError("start_date must be <= end_date")


def _validate_non_empty_string(value: str, field_name: str) -> None:
    """
    Validate that a field is a non-empty string.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_compartments_list(compartments_list: List[str]) -> None:
    """
    Validate that compartments_list is a non-empty list of non-empty strings.
    """
    if not isinstance(compartments_list, list) or not compartments_list:
        raise ValueError("compartments_list must be a non-empty list of strings")
    if any((not isinstance(c, str) or not c.strip()) for c in compartments_list):
        raise ValueError("compartments_list must contain only non-empty strings")


def _execute_tool(op_name: str, fn, *args, **kwargs) -> Dict[str, Any]:
    """
    Execute a tool operation with uniform error logging and mapping.

    Returns:
        The function output on success, or {"error": "<message>"} on failure.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.error("Error in %s: %s", op_name, e)
        return {"error": str(e)}


#
# MCP tools definition
#
# results are wrapped
#
@mcp.tool
def usage_summary_by_service(start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Return the total consumption aggregated by service within a specified time period.

    Args:
        start_date (str): Start date of the period, in ISO format (YYYY-MM-DD).
        end_date (str): End date of the period, in ISO format (YYYY-MM-DD).
            The time window between start_date and end_date must not exceed 93 days.

    Returns:
        dict: A structured dictionary containing consumption details aggregated by service.
            On error returns: {"error": "<message>"}.

    Raises:
        ValueError: If dates are invalid.
    """

    if DEBUG:
        logger.info("Called usage_summary_by_service...")

    try:
        _validate_date_range(start_date, end_date)
    except Exception as e:
        logger.error("Error in usage_summary_by_service validation: %s", e)
        return {"error": str(e)}
    return _execute_tool(
        "usage_summary_by_service",
        usage_summary_by_service_structured,
        start_date,
        end_date,
    )


@mcp.tool
def usage_summary_by_compartment(start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Return the total consumption aggregated by compartment within a specified period.

    Args:
        start_date (str): Start date of the period, in ISO format (YYYY-MM-DD).
        end_date (str): End date of the period, in ISO format (YYYY-MM-DD).
            The time window between start_date and end_date must not exceed 93 days.

    Returns:
        dict: A structured dictionary containing consumption details aggregated by compartment.
            On error returns: {"error": "<message>"}.

    Raises:
        ValueError: If dates are invalid.
    """
    if DEBUG:
        logger.info("Called usage_summary_by_compartment...")

    try:
        _validate_date_range(start_date, end_date)
    except Exception as e:
        logger.error("Error in usage_summary_by_compartment validation: %s", e)
        return {"error": str(e)}
    return _execute_tool(
        "usage_summary_by_compartment",
        usage_summary_by_compartment_structured,
        start_date,
        end_date,
    )


@mcp.tool
def usage_breakdown_for_service_by_compartment(
    start_date: str, end_date: str, service_name: str
) -> Dict[str, Any]:
    """
    Return the consumption for a specific service within a given time period,
    broken down by compartment.

    Args:
        start_date (str): Start date of the period, in ISO format (YYYY-MM-DD).
        end_date (str): End date of the period, in ISO format (YYYY-MM-DD).
            The time window between start_date and end_date must not exceed 93 days.
        service_name (str): Name of the service to filter by.
            Case-insensitive and substring matches are allowed.

    Returns:
        dict: A structured dictionary containing consumption details by compartment.
            Each entry corresponds to one compartment.
            On error returns: {"error": "<message>"}.

    Raises:
        ValueError: If dates are invalid or service_name is empty.
    """
    try:
        _validate_date_range(start_date, end_date)
        _validate_non_empty_string(service_name, "service_name")
    except Exception as e:
        logger.error(
            "Error in usage_breakdown_for_service_by_compartment validation: %s", e
        )
        return {"error": str(e)}
    return _execute_tool(
        "usage_breakdown_for_service_by_compartment",
        fetch_consumption_by_compartment,
        start_date,
        end_date,
        service_name,
    )


@mcp.tool
def usage_breakdown_for_compartment_by_service(
    start_date: str, end_date: str, compartment_name: str
) -> Dict[str, Any]:
    """
    Return the consumption for a specific compartment within a given time period,
    broken down by service.

    Args:
        start_date (str): Start date of the period, in ISO format (YYYY-MM-DD).
        end_date (str): End date of the period, in ISO format (YYYY-MM-DD).
            The time window between start_date and end_date must not exceed 93 days.
        compartment_name (str): Name of the compartment to filter by.
            Case-insensitive and substring matches are allowed.

    Returns:
        dict: A structured dictionary containing consumption details by service.
            Each entry corresponds to one service.
            On error returns: {"error": "<message>"}.

    Raises:
        ValueError: If dates are invalid or compartment_name is empty.
    """
    try:
        _validate_date_range(start_date, end_date)
        _validate_non_empty_string(compartment_name, "compartment_name")
    except Exception as e:
        logger.error(
            "Error in usage_breakdown_for_compartment_by_service validation: %s", e
        )
        return {"error": str(e)}
    return _execute_tool(
        "usage_breakdown_for_compartment_by_service",
        usage_summary_by_service_for_compartment,
        start_date,
        end_date,
        compartment_name,
    )


@mcp.tool
def list_adb_for_compartment(compartment_name: str) -> Dict[str, Any]:
    """
    Return the list of Autonomous Databases in a given compartment.

    Args:
        compartment_name (str): Name of the compartment to filter by.
            Case-insensitive and substring matches are allowed.

    Returns:
        dict: A structured dictionary containing Autonomous Database details.
            Each entry corresponds to one Autonomous Database.
            On error returns: {"error": "<message>"}.

    Raises:
        ValueError: If compartment_name is empty or not found.
    """
    try:
        _validate_non_empty_string(compartment_name, "compartment_name")
    except Exception as e:
        logger.error("Error in list_adb_for_compartment validation: %s", e)
        return {"error": str(e)}

    def _op() -> Dict[str, Any]:
        compartment_id = get_compartment_id_by_name(compartment_name)
        if not compartment_id:
            raise ValueError(f"Compartment '{compartment_name}' not found")
        adbs = list_adbs_in_compartment(compartment_id)
        return {"autonomous_databases": adbs}

    return _execute_tool("list_adb_for_compartment", _op)


@mcp.tool
def list_adb_for_compartments_list(compartments_list: List[str]) -> Dict[str, Any]:
    """
    Return the list of Autonomous Databases for a list of compartments.

    Args:
        compartments_list (list): List of compartment names.

    Returns:
        dict: A structured dictionary containing Autonomous Database details for each compartment.
            Each entry corresponds to a compartment.
            On error returns: {"error": "<message>"}.

    Raises:
        ValueError: If compartments_list is empty or contains invalid values.
    """
    try:
        _validate_compartments_list(compartments_list)
    except Exception as e:
        logger.error("Error in list_adb_for_compartments_list validation: %s", e)
        return {"error": str(e)}
    return _execute_tool(
        "list_adb_for_compartments_list",
        list_adbs_in_compartment_list,
        compartments_list,
    )


#
# Run the Select AI MCP server
#
if __name__ == "__main__":
    run_server(mcp)
