"""
MCP Server to query data regarding OCI usage and consumption
"""

from typing import Any, Dict

# here is the function that calls Select AI
from consumption_utils import (
    usage_summary_by_service_structured,
    usage_summary_by_compartment_structured,
    fetch_consumption_by_compartment,
    usage_summary_by_service_for_compartment,
)
from mcp_utils import create_server, run_server
from utils import get_console_logger

from config import DEBUG

logger = get_console_logger()

mcp = create_server("OCI Consumption MCP server")


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

    Raises:
        Error: If the time period exceeds 93 days, or any other errors occurs.
    """

    if DEBUG:
        logger.info("Called usage_summary_by_service...")

    try:
        results = usage_summary_by_service_structured(start_date, end_date)
    except Exception as e:
        logger.error("Error generating consumption: %s", e)
        results = {"error": str(e)}

    return results


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

    Raises:
        Error: If the time period exceeds 93 days, or any other errors occurs.
    """
    if DEBUG:
        logger.info("Called usage_summary_by_compartment...")

    try:
        results = usage_summary_by_compartment_structured(start_date, end_date)
    except Exception as e:
        logger.error("Error generating consumption: %s", e)
        results = {"error": str(e)}

    return results


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

    Raises:
        Error: If the time period exceeds 93 days, or any other errors occurs.
    """
    try:
        results = fetch_consumption_by_compartment(start_date, end_date, service_name)
    except Exception as e:
        logger.error("Error generating breakdown: %s", e)
        results = {"error": str(e)}

    return results


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
    Raises:
        Error: If the time period exceeds 93 days, or any other errors occurs.
    """
    try:
        results = usage_summary_by_service_for_compartment(
            start_date, end_date, compartment_name
        )
    except Exception as e:
        logger.error("Error generating breakdown: %s", e)
        results = {"error": str(e)}

    return results


#
# Run the Select AI MCP server
#
if __name__ == "__main__":
    run_server(mcp)
