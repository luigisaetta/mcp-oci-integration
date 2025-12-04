"""
Streaming sanity check for llm_with_mcp (no simulated chunking).

Usage:
    python test_llm_with_mcp_streaming_no_chunks.py

Requires:
    - llm_with_mcp.py in the same directory
    - llm_with_mcp exports: run, run_streaming_sync, StreamEvent
"""

import sys
import json
from typing import Dict

from llm_with_mcp import run, run_streaming_sync, StreamEvent

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
# Streaming test (no chunks)
# -------------------------
def test_streaming_no_chunks() -> None:
    """
    Streaming test without simulated chunking.
    """
    question = QUESTION
    history = []

    print("\n=== STREAMING TEST (NO CHUNKS) ===")
    print(f"[USER] {question}\n")
    print("[ASSISTANT] ", end="", flush=True)

    # Counters to verify behavior
    counters: Dict[str, int] = {
        "start": 0,
        "tool_call": 0,
        "tool_result": 0,
        "tool_error": 0,
        "answer_chunk": 0,
        "final_answer": 0,
    }

    def handle_event(ev: StreamEvent) -> None:
        t = ev["type"]
        counters[t] = counters.get(t, 0) + 1

        if t == "start":
            # Already printed the user question above, nothing else needed here
            pass

        elif t == "tool_call":
            print("\n[TOOL_CALL]", ev["tool"], ev["args"])
            print("[ASSISTANT] ", end="", flush=True)

        elif t == "tool_result":
            print("\n[TOOL_RESULT]", ev["tool"])
            print("[ASSISTANT] ", end="", flush=True)

        elif t == "tool_error":
            print("\n[TOOL_ERROR]", ev["tool"], "->", ev["payload"])
            print("[ASSISTANT] ", end="", flush=True)

        elif t == "answer_chunk":
            # This should NOT happen anymore with the new implementation
            chunk = ev.get("payload", "")
            sys.stdout.write(chunk)
            sys.stdout.flush()

        elif t == "final_answer":
            print("\n\n[FINAL ANSWER RECEIVED]")
            print(ev["answer"])
            # If you want to inspect metadata, uncomment:
            # print("\n[METADATA]", json.dumps(ev.get("metadata", {}), indent=2, ensure_ascii=False))

        else:
            print("\n[UNKNOWN EVENT]", ev)

    # Run the streaming wrapper synchronously
    run_streaming_sync(
        question=question,
        history=history,
        on_event=handle_event,
    )

    # Summary and simple sanity checks
    print("\n=== STREAMING SUMMARY ===")
    print(json.dumps(counters, indent=2))

    # Soft assertions (do not raise, just print diagnostics)
    if counters["final_answer"] != 1:
        print(
            f"[WARNING] Expected exactly 1 final_answer event, got {counters['final_answer']}"
        )

    if counters["answer_chunk"] != 0:
        print(
            f"[WARNING] Expected 0 answer_chunk events, got {counters['answer_chunk']}"
        )

    if counters["tool_error"] > 0:
        print(f"[WARNING] There were {counters['tool_error']} tool_error events")


# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    # 1) Non-streaming baseline
    # asyncio.run(test_non_streaming())
    print()

    # 2) Streaming test without simulated chunking
    test_streaming_no_chunks()
