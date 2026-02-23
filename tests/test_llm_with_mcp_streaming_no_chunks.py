"""
Non-streaming sanity check for llm_with_mcp.

Usage:
    python test_llm_with_mcp_streaming_no_chunks.py

Requires:
    - llm_with_mcp.py in the same directory
    - llm_with_mcp exports: run
"""

import json

from llm_with_mcp import run

QUESTION = (
    "Mostrami lo usage (amount) per il compartment lsaetta nel primo semestre del 2025"
)


# -------------------------
# Non-streaming test
# -------------------------
async def test_non_streaming() -> None:
    """
    Simple non-streaming test for baseline comparison.
    """
    question = QUESTION
    history = []

    print("\n=== NON-STREAMING TEST ===")
    print(f"[USER] {question}\n")

    result = await run(question, history)
    answer = result["answer"]
    metadata = result.get("metadata", {})

    print("[ASSISTANT]\n")
    print(answer)

    print("\n[METADATA]")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))


# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    import asyncio

    asyncio.run(test_non_streaming())
