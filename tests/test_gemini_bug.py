import asyncio
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_oci import ChatOCIGenAI

# with model1 after a long time it gives error 500
MODEL1 = "google.gemini-2.5-pro"
# with model2 it works fine
MODEL2 = "openai.gpt-oss-120b"

MODELS_WITHOUT_KWARGS = {
    "openai.gpt-oss-120b",
    "openai.gpt-5",
    "openai.gpt-4o-search-preview",
    "openai.gpt-4o-search-preview-2025-03-11",
}

SERVICE_ENDPOINT = "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com"
AUTH = "API_KEY"
COMPARTMENT_ID = "ocid1.compartment.oc1..yourocid"

def get_llm(model_id=MODEL1, temperature=0., max_tokens=2048):
    """
    Initialize and return an instance of ChatOCIGenAI with the specified configuration.

    Returns:
        ChatOCIGenAI: An instance of the OCI GenAI language model.
    """
    if model_id not in MODELS_WITHOUT_KWARGS:
        _model_kwargs = {
            "temperature": temperature,
            "max_tokens": max_tokens
        }
    else:
        # for some models (OpenAI search) you cannot set those params
        _model_kwargs = None

    llm = ChatOCIGenAI(
        auth_type=AUTH,
        model_id=model_id,
        service_endpoint=SERVICE_ENDPOINT,
        compartment_id=COMPARTMENT_ID,
        # changed to solve OpenAI/Grok4 issue
        is_stream=True,
        model_kwargs=_model_kwargs,
    )
    return llm



async def main():
    # ---------------------------------------------------
    # Load the OCI model using your LangChain integration
    # ---------------------------------------------------
    llm = get_llm(model_id=MODEL1)  # change model name as needed

    # ---------------------------------------------------
    # 1) Initial user request
    # ---------------------------------------------------
    user_msg = HumanMessage(content="What's the weather in Rome?")

    # ---------------------------------------------------
    # 2) Simulated tool call emitted by an LLM
    # ---------------------------------------------------
    fake_tool_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "1",  # required by LangChain + OCI
                "name": "get_weather",
                "args": {"city": "Rome", "units": "metric"},
            }
        ],
    )

    # ---------------------------------------------------
    # 3) ToolMessage responding to the toolCallId "1"
    #    (this is what OCI requires between toolCalls and next assistant msg)
    # ---------------------------------------------------
    tool_result_msg = ToolMessage(
        content='{"temperature": 20, "condition": "sunny"}',
        tool_call_id="1",
        name="get_weather",
    )


    # ---------------------------------------------------
    # Build conversation
    # ---------------------------------------------------
    messages = [
        user_msg,
        fake_tool_call,
        tool_result_msg,
        # empty_ai_msg,
    ]

    print("\n=== Sending messages to LLM ===")
    for m in messages:
        print(type(m), m.model_dump())

    print("\n=== Invoking OCI LLM through LangChain ===")
    response = await llm.ainvoke(messages)

    print("\n=== Raw LLM Response ===")
    print(response)
    print("\nResponse content:", response.content)
    
    print("Tool calls:", getattr(response, "tool_calls", None))


if __name__ == "__main__":
    asyncio.run(main())
