"""
Agent API simple client
"""

from datetime import datetime
import requests

# adjust if needed
API_URL = "http://130.61.38.113:8001/ask"
TIMEOUT = 60


def ask(question: str, history=None):
    """
    Calls the MCP Agent FastAPI endpoint using the requests library.
    """
    history = history or []

    payload = {"question": question, "history": history}

    resp = requests.post(API_URL, json=payload, timeout=TIMEOUT)

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")

    data = resp.json()

    # Expected format: {"answer": "..."}
    return data.get("answer")


if __name__ == "__main__":
    # Example usage
    HISTORY = [
        {"role": "user", "content": "We are analyzing OCI usage."},
        {"role": "assistant", "content": "Sure, I can help with that."},
    ]
    QUESTION = """Give me top 10 compartments by usage (amount) this month.
    Put data in a table. Don't add quantity.
    Anonymize: take only the first 3 letters for the name of the compartment 
    and replace all the others to x.
    """
    DIR = "./reports"
    TODAY = datetime.now().strftime("%Y%m%d")

    FILENAME = f"{DIR}/finops_usage_report_{TODAY}.md"

    print("")
    print("Question: ", QUESTION)
    print("Thinking...")
    print("")

    # calling the API
    answer = ask(QUESTION, HISTORY)

    print("Answer:")
    print(answer)
    print("")

    # save to file in the Object Storage (using object mount)
    with open(FILENAME, "w", encoding="utf-8") as f:
        f.write(str(answer))
