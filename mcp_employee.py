"""
Simulate an MCP server giving access to Employeee API
"""

from typing import Any, Dict

from employee_api import get_employee, list_employees
from mcp_utils import create_server, run_server
from utils import get_console_logger

from config import (
    DEBUG,
)


logger = get_console_logger()

mcp = create_server("OCI HCM MCP server")


#
# MCP tools definition
# add and write the code for the tools here
# mark each tool with the annotation
#
# results are wrapped
#
@mcp.tool
def get_employee_info(identifier: str | int) -> Dict[str, Any]:
    """
    Return employee data.

    Args:
        identifier: employee id or full name.

    Returns:
        dict: data regarding employee.

    Examples:
        >>> get_employee_info(1010)
        {
            "employee_id": 1010,
            "employee_name": "Jakob Johansson",
            "dept_name": "Security Engineering",
            "location": "Stockholm, Sweden",
            "employee_level": "IC3",
            "vacation_days_taken": 9,
        }
    """
    if DEBUG:
        logger.info("Called get_employee_info...")

    try:
        # in a real case we should call here HCM API
        results = get_employee(identifier)
    except Exception as e:
        logger.error("Error getting data for employee: %s, error: %s", identifier, e)
        results = {"error": str(e)}

    return results


@mcp.tool
def get_all_employees_info() -> dict:
    """
    Return the list of all employees.

    Returns:
        list[dict]: List of employee dictionaries.

    Examples:
        >>> get_all_employees_info()
        {
            "ok": True,
            "employees":
            [
                {
                    "employee_id": 1001,
                    "employee_name": "Alice Johnson",
                    "dept_name": "Engineering",
                    "location": "New York, USA",
                    "employee_level": "IC5",
                    "vacation_days_taken": 15,
                },
                ...
            ],
            "error": None
        }
    """
    if DEBUG:
        logger.info("Called get_all_employees_info...")

    try:
        # in a real case we should call here HCM API
        employees = list_employees()

        # be careful the format of the output must be the same in the two branches!
        # otherwise you get a serialization error
        result = {"ok": True, "employees": employees, "error": None}
    except Exception as e:
        logger.error("Error getting data for all employees: %s", e)
        result = {"ok": False, "employees": [], "error": str(e)}

    return result


#
# Run the Employee MCP server
#
if __name__ == "__main__":
    run_server(mcp)
