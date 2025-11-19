"""
MCP server exposing read-only access to a GitHub repository.

Tools provided:

1. list_repo_items
   - List files and folders inside a given path of a GitHub repository.
   - Useful to explore the repo structure (root or subdirectories).

2. get_file_content
   - Read the content of a file (text) from the repository.

Semantics:

- repo_full_name può essere:
    * None / ""              -> usa GITHUB_DEFAULT_REPO (+ GITHUB_USERNAME se serve)
    * "mcp-oci-integration"  -> viene normalizzato a "luigisaetta/mcp-oci-integration"
    * "owner/repo"           -> usato così com'è

Tutta la normalizzazione e accesso GitHub è gestita da github_utils.
"""

from typing import Any, Dict, List, Optional
import logging

from mcp_utils import create_server, run_server
from github_utils import (
    GithubConfigError,
    list_directory,
    get_file_content as _get_file_content,
)
from utils import get_console_logger

logger = get_console_logger()

mcp = create_server("Github MCP")


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
        items = list_directory(
            repo_full_name=repo_full_name,
            path=path,
            ref=ref,
        )
        logger.info("MCP list_repo_items returning %d items", len(items))
        return {"items": items}
    except GithubConfigError as e:
        logger.error("GitHub configuration error in list_repo_items: %s", e)
        raise RuntimeError(f"GitHub configuration error: {e}") from e
    except Exception as e:  # noqa: BLE001
        logger.error("Generic error in list_repo_items: %r", e)
        raise RuntimeError(f"Error listing repo items: {e}") from e


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
        logger.error("GitHub configuration error in get_file_content: %s", e)
        raise RuntimeError(f"GitHub configuration error: {e}") from e
    except FileNotFoundError as e:
        logger.error("File not found in get_file_content: %s", e)
        raise RuntimeError(f"File not found or not a regular file: {e}") from e
    except Exception as e:  # noqa: BLE001
        logger.error("Generic error in get_file_content: %r", e)
        raise RuntimeError(f"Error getting file content: {e}") from e


if __name__ == "__main__":
    # normale start MCP
    run_server(mcp)
