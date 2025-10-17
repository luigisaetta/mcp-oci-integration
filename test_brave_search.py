"""
test_brave_search.py

Quick test for BraveSearchClient.
"""

import os
from brave_search_client import BraveSearchClient


def main():
    """Simple test for BraveSearchClient."""
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        print("Please set BRAVE_API_KEY environment variable.")
        return

    client = BraveSearchClient(api_key)
    query = "Climate change impacts on agriculture"
    results, meta = client.search(query, count=5, vertical="web")

    print(f"\n🔎 Query: {query}")
    print(f"🌍 Meta: {meta}\n")

    for r in results:
        print(f"{r.rank}. {r.title}")
        print(f"   {r.url}")
        if r.snippet:
            print(f"   → {r.snippet[:120]}...")
        print()


if __name__ == "__main__":
    main()
