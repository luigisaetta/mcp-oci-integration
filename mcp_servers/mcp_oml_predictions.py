"""
This is an MCP Server that calls an OML model for prediction.

In the demo: F1 race predictions based on team budget, driver age, etc.
"""

from typing import Dict, Any

from oml_utils import get_predictions
from mcp_utils import create_server, run_server


mcp = create_server("OCI MCP OML Predictions")


#
# MCP tools definition
# add and write the code for the tools here
# mark each tool with the annotation
#
@mcp.tool
def oml_predict(
    race_year: str = "2024",
    total_points: str = "250",
    team_budget: str = "100",
    driver_age: str = "27",
) -> Dict[str, Any]:
    """
    Return the result of OML predictions for
    the provided input parameters.

    Args:
        race_year (str): the race year.
        total_points (str): total points so far.
        team_budget (str): team budget in million $.
        driver_age (str): driver age in years.

    Returns:
        dict: prediction results from OML.

    """
    results = get_predictions(
        int(race_year), float(total_points), int(team_budget), int(driver_age)
    )

    return {"race_position": results}


#
# Run the MCP server
#
if __name__ == "__main__":
    run_server(mcp)
