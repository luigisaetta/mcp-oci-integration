"""
File name: config.py
Author: Luigi Saetta
Date last modified: 2026-02-12
Python Version: 3.11

Description:
    This module provides general configurations
    (12/02/2026) updated to use env vars, if present


Usage:
    Import this module into other scripts to use its functions.
    Example:
        import config

License:
    This code is released under the MIT License.

Notes:
    This is a part of a demo showing how to implement an advanced
    RAG solution as a LangGraph agent.

Warnings:
    This module is in development, may change in future versions.
"""

import os
from typing import List


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_list(name: str, default: List[str]) -> List[str]:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


DEBUG = _env_bool("DEBUG", False)
STREAMING = _env_bool("STREAMING", False)
USERNAME = _env_str("USERNAME", "Luigi")

# type of OCI auth
AUTH = _env_str("AUTH", "API_KEY")

# embeddings
# added this to distinguish between Cohere and REST NVIDIA models
# can be OCI or NVIDIA
EMBED_MODEL_TYPE = _env_str("EMBED_MODEL_TYPE", "OCI")
# EMBED_MODEL_TYPE = "NVIDIA"
# "cohere.embed-multilingual-v3.0"
EMBED_MODEL_ID = _env_str("EMBED_MODEL_ID", "cohere.embed-v4.0")

# this one needs to specify the dimension, default is 1536
# EMBED_MODEL_ID = "cohere.embed-v4.0"
# used only for NVIDIA models
NVIDIA_EMBED_MODEL_URL = _env_str("NVIDIA_EMBED_MODEL_URL", "")


# LLM
# this is the default model
# changed to align CHI and FRA
LLM_MODEL_ID = _env_str("LLM_MODEL_ID", "openai.gpt-oss-120b")
TEMPERATURE = _env_float("TEMPERATURE", 0.0)
TOP_P = _env_float("TOP_P", 1.0)
MAX_TOKENS = _env_int("MAX_TOKENS", 4000)

# OCI general
REGION = _env_str("REGION", "us-chicago-1")
# REGION = "us-chicago-1"

# (11/12/2025) introduced to support the switch to langchain OpenAI integration
USE_LANGCHAIN_OPENAI = _env_bool("USE_LANGCHAIN_OPENAI", False)

# REGION = "us-chicago-1"
SERVICE_ENDPOINT = _env_str(
    "SERVICE_ENDPOINT", f"https://inference.generativeai.{REGION}.oci.oraclecloud.com"
)

if REGION == "us-chicago-1":
    # for now only available in chicago region
    model_list_default = [
        "xai.grok-4-1-fast-reasoning",
        "openai.gpt-5.2",
        "openai.gpt-oss-120b",
        "google.gemini-2.5-pro",
    ]
else:
    model_list_default = ["openai.gpt-oss-120b", "google.gemini-2.5-pro"]

MODEL_LIST = _env_list("MODEL_LIST", model_list_default)

# semantic search
TOP_K = _env_int("TOP_K", 10)
COLLECTION_LIST = _env_list("COLLECTION_LIST", ["BOOKS", "NVIDIA_BOOKS2"])
DEFAULT_COLLECTION = _env_str("DEFAULT_COLLECTION", "FINOPS")


# history management (put -1 if you want to disable trimming)
# consider that we have pair (human, ai) so use an even (ex: 6) value
MAX_MSGS_IN_HISTORY = _env_int("MAX_MSGS_IN_HISTORY", 20)

# reranking enabled or disabled from UI

# for loading
CHUNK_SIZE = _env_int("CHUNK_SIZE", 4000)
CHUNK_OVERLAP = _env_int("CHUNK_OVERLAP", 100)

# for MCP server
TRANSPORT = _env_str("TRANSPORT", "streamable-http")
# bind to all interfaces
HOST = _env_str("HOST", "0.0.0.0")
PORT = _env_int("PORT", 9000)

# with this we can toggle JWT token auth
ENABLE_JWT_TOKEN = _env_bool("ENABLE_JWT_TOKEN", True)

# can be OCI_IAM or IBM_CONTEXT_FORGE
# JWT_TOKEN_PROVIDER = "IBM_CONTEXT_FORGE"
JWT_TOKEN_PROVIDER = _env_str("JWT_TOKEN_PROVIDER", "OCI_IAM")

# for OCI_IAM put your domain URL here
IAM_BASE_URL = _env_str(
    "IAM_BASE_URL",
    "https://idcs-930d7b2ea2cb46049963ecba3049f509.identity.oraclecloud.com",
)
# these are used during the verification of the token
ISSUER = _env_str("ISSUER", "https://identity.oraclecloud.com/")
AUDIENCE = _env_list(
    "AUDIENCE",
    ["urn:opc:lbaas:logicalguid=idcs-930d7b2ea2cb46049963ecba3049f509"],
)

# for Select AI
# SELECT_AI_PROFILE = "OCI_GENERATIVE_AI_PROFILE_F1"
# this one with SH schema
SELECT_AI_PROFILE = _env_str("SELECT_AI_PROFILE", "OCI_GENERATIVE_AI_PROFILE_BANKS")

# APM integration
ENABLE_TRACING = _env_bool("ENABLE_TRACING", False)
OTEL_SERVICE_NAME = _env_str("OTEL_SERVICE_NAME", "llm-mcp-agent")
OCI_APM_TRACES_URL = _env_str(
    "OCI_APM_TRACES_URL",
    "https://aaaadec2jjn3maaaaaaaaach4e.apm-agt.eu-frankfurt-1.oci.oraclecloud.com/20200101/opentelemetry/private/v1/traces",
)

# UI
UI_TITLE = _env_str("UI_TITLE", "🛠️ AI Assistant powered by MCP")

# Agent API
AGENT_API_HOST = _env_str("AGENT_API_HOST", "0.0.0.0")
AGENT_API_PORT = _env_int("AGENT_API_PORT", 8001)

# Github integration
GITHUB_DEFAULT_REPO = _env_str("GITHUB_DEFAULT_REPO", "mcp-oci-integration")
