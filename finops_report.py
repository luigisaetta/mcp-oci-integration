"""
Generate a FinOps usage report for November 2025, aggregating specific compartments and forecasting usage.
"""

import asyncio
from datetime import datetime
from llm_with_mcp import run

if __name__ == "__main__":
    # A single, multi-line prompt (triple quotes avoids accidental string concatenation issues)
    QUESTION = """
Give me top 20 compartments for usage (amount) in the month of November 2025. 
Put all the data in a table. 


In addition, before deciding the top 20, do some aggregation: 
* aggregate the costs for mgueury and devops and put the total under the name mgueury 
* aggregate the costs for omasalem and ADBAGENT and put the total under omasalem
* aggregate the costs for matwolf and ai-test-oke and put the result under the name matwolf
* aggregate the costs for lsaetta and lsaetta-apm and put the result under the name lsaetta. 

Add a final row to the table with the overall total. Return only the table with an heading, 
no additional comments or explanation.
"""
    HISTORY = []

    agent_result = asyncio.run(run(QUESTION, history=HISTORY))

    print("")
    print(agent_result["answer"])
    print("")
    print("Tools called:", agent_result["metadata"]["tool_names"])
    print("")

    DIR = "reports"
    today = datetime.now().strftime("%Y%m%d")
    FILENAME = f"./{DIR}/finops_usage_report_{today}.md"

    with open(FILENAME, "w", encoding="utf-8") as f:
        f.write(str(agent_result["answer"]))

    print(f"\nMarkdown table saved to {FILENAME}")
