"""
Agent API
"""

from typing import List, Literal, Dict, Any
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

# import the async run() from your existing module
from llm_with_mcp import run

from config import AGENT_API_HOST, AGENT_API_PORT

# define the api
app = FastAPI(title="LLM_WITH_MCP Agent API")


# ---- Pydantic models ----


class HistoryMessage(BaseModel):
    """
    Class for History messages
    """

    role: Literal["user", "assistant", "system", "tool"]
    content: str


class AskRequest(BaseModel):
    """
    Model for input
    """

    question: str
    history: List[HistoryMessage] = []


class AskResponse(BaseModel):
    """
    Model for output
    """

    # answer is a markdown string
    answer: str


# ---- Routes ----
@app.get("/health")
async def health():
    """
    Healthcheck
    """
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    """
    Call the MCP agent with a question and an optional history.
    """
    # convert Pydantic objects to the simple dict format expected by _build_messages
    history_dicts: List[Dict[str, Any]] = [msg.dict() for msg in req.history]

    answer = await run(req.question, history=history_dicts)
    return AskResponse(answer=answer)


if __name__ == "__main__":
    # Run with: python agent_api.py
    uvicorn.run("agent_api:app", host=AGENT_API_HOST, port=AGENT_API_PORT, reload=True)
