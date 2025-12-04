"""
Simple manual test harness for llm_with_mcp.

Usage:
    python test_llm_with_mcp.py

Assumes:
    - llm_with_mcp.py is in the same directory
    - exports: run, run_streaming_sync, StreamEvent, AgentWithMCP, build_system_prompt
"""

import sys
import json
import asyncio

from langchain_core.messages import SystemMessage, HumanMessage

from llm_with_mcp import (
    run,
    run_streaming_sync,
    StreamEvent,
    AgentWithMCP,
    build_system_prompt,
)


QUESTION = "Show me usage (amount) for lsaetta compartment in september, october and november 2025"


# -------------------------
# 1) Non-streaming test
# -------------------------
async def test_non_streaming():
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
# 2) Streaming test (simulated final answer)
# -------------------------
def test_streaming():
    question = QUESTION
    history = []

    print("\n=== STREAMING TEST (CURRENT answer_streaming) ===")
    print(f"[USER] {question}\n")
    print("[ASSISTANT] ", end="", flush=True)

    final_counter = {"count": 0}

    def handle_event(ev: StreamEvent):
        t = ev["type"]

        if t == "start":
            # already printed the question above
            pass

        elif t == "tool_call":
            # temporarily break the assistant line to show the tool call
            print("\n[TOOL_CALL]", ev["tool"], ev["args"])
            print("[ASSISTANT] ", end="", flush=True)

        elif t == "tool_result":
            print("\n[TOOL_RESULT]", ev["tool"])
            print("[ASSISTANT] ", end="", flush=True)

        elif t == "tool_error":
            print("\n[TOOL_ERROR]", ev["tool"], "->", ev["payload"])
            print("[ASSISTANT] ", end="", flush=True)

        elif t == "answer_chunk":
            chunk = ev.get("payload", "")
            sys.stdout.write(chunk)
            sys.stdout.flush()

        elif t == "final_answer":
            final_counter["count"] += 1
            print("\n\n[FINAL ANSWER RECEIVED]")
            print(ev["answer"])
            # If you want to inspect metadata, uncomment:
            # print("\n[METADATA]", json.dumps(ev.get("metadata", {}), indent=2, ensure_ascii=False))

        else:
            print("\n[UNKNOWN EVENT]", ev)

    run_streaming_sync(
        question=question,
        history=history,
        on_event=handle_event,
    )


# -------------------------
# 3) New test:
#    true streaming of the final answer (2-stage approach)
# -------------------------
async def test_stream_final_from_tools():
    """
    Two-stage test:

    1) Use the normal tool-based agent (answer) to:
       - call tools
       - collect tool_results reliably
    2) Build a new prompt from:
       - original question
       - tool_results
    3) Call _stream_llm_messages(...) to stream the final answer text
       based only on those tool results, with real token streaming.
    """
    question = QUESTION
    history = []

    print("\n=== TOOL LOOP (NON-STREAMING, COLLECT RESULTS) ===")
    print(f"[USER] {question}\n")

    # Stage 1: normal tool loop (non-streaming)
    agent = await AgentWithMCP.create()
    result = await agent.answer(question, history)
    answer = result["answer"]
    metadata = result.get("metadata", {})
    tool_results = metadata.get("tool_results", [])

    print("[DEBUG] Non-streaming final answer (from answer()):")
    print(answer)

    print("\n[DEBUG] Tool results used for stage 2:")
    print(json.dumps(tool_results, indent=2, ensure_ascii=False))

    # Build a textual summary of tool results to feed the LLM in stage 2
    tool_summary_lines = []
    for tr in tool_results:
        name = tr.get("tool")
        args = tr.get("args", {})
        result_payload = tr.get("result")
        error_payload = tr.get("error")

        if result_payload is not None:
            snippet = json.dumps(result_payload, ensure_ascii=False)
        else:
            snippet = f"ERROR: {error_payload}"

        tool_summary_lines.append(
            f"- Tool `{name}` called with args "
            f"{json.dumps(args, ensure_ascii=False)} returned:\n{snippet}"
        )

    tool_summary = "\n".join(tool_summary_lines) or "No tools were used."

    # Stage 2: build new messages and stream the final answer
    system_prompt = build_system_prompt()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=(
                "The user asked:\n"
                f"{question}\n\n"
                "You have already executed the following tools:\n"
                f"{tool_summary}\n\n"
                "Using ONLY these results, now generate the best possible final answer. "
                "Do not call or mention tools in your answer.\n"
            )
        ),
    ]

    print("\n=== STREAMING FINAL ANSWER FROM TOOL RESULTS (TRUE LLM STREAM) ===")
    print("[ASSISTANT] ", end="", flush=True)

    async for piece in agent._stream_llm_messages(messages):
        sys.stdout.write(piece)
        sys.stdout.flush()

    print("\n\n[END STREAM]")


# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    # 1) Test non-streaming
    # asyncio.run(test_non_streaming())
    print()

    # 2) Test streaming with current answer_streaming (simulated final chunking)
    # test_streaming()
    print()

    # 3) Test true streaming of the final answer, using tool_results
    asyncio.run(test_stream_final_from_tools())
