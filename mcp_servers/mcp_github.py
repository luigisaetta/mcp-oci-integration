"""
File name: mcp_github.py
Author: Luigi Saetta
Date last modified: 2025-02-11
Python Version: 3.11

Description:
    This module implements an MCP (Model Context Protocol) server for GitHub repository interactions.
    It provides tools to list files and directories in a repository (with optional refs like branches or commits)
    and retrieve the content of specific files, using GitHub API with repo normalization and authentication handling.

Usage:
    Import this module to use its tools or run it as a standalone MCP server.
    Example:
        from mcp_servers.mcp_github import list_repo_items

        items = list_repo_items(repo_full_name="owner/repo", path=".")
        # Or run the server: python mcp_github.py

License:
    This code is released under the MIT License.

Notes:
    This is part of the MCP-OCI integration framework and relies on GitHub API utilities.
    Tools support default repo configs and return structured dictionaries for easy integration with MCP agents.

Warnings:
    This module is in development and may change in future versions. Ensure GitHub authentication (e.g., tokens) is configured
    to avoid API rate limits or access errors, and handle private repos appropriately.
"""

from typing import Any, Dict, Optional
import re

from mcp_utils import create_server, run_server
from github_utils import (
    GithubConfigError,
    list_directory,
    get_file_content as _get_file_content,
)
from utils import get_console_logger

logger = get_console_logger()

mcp = create_server("Github MCP")


def _validate_optional_repo_full_name(repo_full_name: Optional[str]) -> None:
    """
    Validate repo_full_name when explicitly provided.
    Allowed forms:
      - "repo"
      - "owner/repo"
    """
    if repo_full_name is None:
        return

    if not isinstance(repo_full_name, str):
        raise ValueError("repo_full_name must be a string when provided")

    candidate = repo_full_name.strip()
    if not candidate:
        # Empty string is treated as "not provided" (default repo from config).
        return

    if candidate.count("/") > 1:
        raise ValueError("repo_full_name must be in 'repo' or 'owner/repo' format")

    if "/" in candidate:
        owner, repo = candidate.split("/", 1)
        if not owner or not repo:
            raise ValueError("repo_full_name must be in 'owner/repo' format")


def _validate_path(value: str, *, allow_empty: bool, field_name: str = "path") -> None:
    """
    Validate path fields used by MCP tools.
    """
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    if not allow_empty and not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_optional_ref(ref: Optional[str]) -> None:
    """
    Validate optional Git reference (branch/tag/sha).
    """
    if ref is None:
        return
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("ref must be a non-empty string when provided")

    # Conservative safety check against accidental whitespace/control chars.
    if re.search(r"\s", ref):
        raise ValueError("ref must not contain whitespace")


def _execute_tool(op_name: str, fn, *args, **kwargs) -> Dict[str, Any]:
    """
    Execute a tool operation with uniform error logging and mapping.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        logger.error("Error in %s: %s", op_name, e)
        return {"error": str(e)}


@mcp.tool()
def list_repo_items(
    repo_full_name: Optional[str] = None,
    path: str = "",
    ref: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List files and directories inside a path of a GitHub repository.

    Args:
        repo_full_name:
            The repository to inspect.
            Can be:
              - null/empty -> default from config (GITHUB_DEFAULT_REPO + GITHUB_USERNAME)
              - "repo"     -> normalized to "<GITHUB_USERNAME>/repo"
              - "owner/repo" -> used as-is

        path:
            Path inside the repository. Use "" or "." for the root.

        ref:
            Optional git reference (branch, tag, commit SHA).
            If omitted, the default branch is used.

    Returns:
        A list of items with:
          - path
          - name
          - type ("file" | "dir")
          - size
          - sha
    """
    logger.info(
        "MCP list_repo_items called with repo_full_name=%r, path=%r, ref=%r",
        repo_full_name,
        path,
        ref,
    )

    try:
        _validate_optional_repo_full_name(repo_full_name)
        _validate_path(path, allow_empty=True)
        _validate_optional_ref(ref)
    except Exception as e:  # noqa: BLE001
        logger.error("Error in list_repo_items validation: %s", e)
        return {"error": str(e)}

    def _op() -> Dict[str, Any]:
        """Execute directory listing and map GitHub-specific errors."""
        try:
            items = list_directory(
                repo_full_name=repo_full_name,
                path=path,
                ref=ref,
            )
            logger.info("MCP list_repo_items returning %d items", len(items))
            return {"items": items}
        except GithubConfigError as e:
            raise RuntimeError(f"GitHub configuration error: {e}") from e

    return _execute_tool("list_repo_items", _op)


@mcp.tool()
def get_file_content(
    repo_full_name: Optional[str] = None,
    path: str = "",
    ref: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve the text content of a file in a GitHub repository.

    Args:
        repo_full_name:
            Same semantics as in list_repo_items().

        path:
            Full path of the file from repo root.

        ref:
            Optional git reference (branch, tag, commit SHA).

    Returns:
        A dict with:
          - path
          - name
          - sha
          - size
          - encoding
          - content (string)
    """
    logger.info(
        "MCP get_file_content called with repo_full_name=%r, path=%r, ref=%r",
        repo_full_name,
        path,
        ref,
    )

    try:
        _validate_optional_repo_full_name(repo_full_name)
        _validate_path(path, allow_empty=False)
        _validate_optional_ref(ref)
    except Exception as e:  # noqa: BLE001
        logger.error("Error in get_file_content validation: %s", e)
        return {"error": str(e)}

    def _op() -> Dict[str, Any]:
        """Execute file-content retrieval and map GitHub-specific errors."""
        try:
            res = _get_file_content(
                repo_full_name=repo_full_name,
                path=path,
                ref=ref,
            )
            logger.info(
                "MCP get_file_content returning file %s (%d bytes)",
                res.get("path"),
                res.get("size") or -1,
            )
            return res
        except GithubConfigError as e:
            raise RuntimeError(f"GitHub configuration error: {e}") from e
        except FileNotFoundError as e:
            raise RuntimeError(f"File not found or not a regular file: {e}") from e

    return _execute_tool("get_file_content", _op)


if __name__ == "__main__":
    # normale start MCP
    run_server(mcp)
