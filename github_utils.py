"""
File name: github_utils.py
Author: Luigi Saetta
Date last modified: 2025-12-08
Python Version: 3.11

Description:
    Utility module providing high-level helper functions for interacting with GitHub
    through the PyGithub library. It provides:
        - Authentication handling (token retrieval and validation)
        - Repository normalization and resolution (owner/repo inference)
        - Functions to list directories and files
        - Functions to retrieve file content with correct decoding
        - Functions to list repository commits, optionally filtered by path or ref

    The module is intentionally independent from MCP / FastMCP to maximize
    reusability and simplify testing. It is used by MCP servers (e.g., mcp_github)
    but can also be imported standalone in any Python application.

Usage:
    Example:
        from github_utils import get_repo, list_directory, get_file_content

        repo = get_repo("myuser/myrepo")
        items = list_directory(repo_full_name="myuser/myrepo", path="src")
        file_info = get_file_content("myuser/myrepo", "README.md")

    Configuration:
        Requires the following variables (from config and config_private):
            - GITHUB_TOKEN
            - GITHUB_USERNAME
            - GITHUB_DEFAULT_REPO

License:
    This code is released under the MIT License.

Notes:
    - Repository names can be automatically expanded using the default configured
      repo or username.
    - Decoding of file content falls back to latin-1 when UTF-8 decoding fails.
    - All returned structures are JSON-friendly dictionaries for easy integration
      with higher-level systems (e.g., MCP agents).

Warnings:
    - Ensure GITHUB_TOKEN is configured; otherwise, GitHubConfigError is raised.
    - Private repositories require appropriate permissions on the provided token.
    - GitHub rate limits apply if token is missing or insufficient.
    - Exceptions from PyGithub are wrapped in GithubConfigError with contextual
      messages to simplify debugging.
"""

from typing import Any, Dict, List, Optional
from github import Github
from github.Repository import Repository
from github.ContentFile import ContentFile

from config import GITHUB_DEFAULT_REPO
from config_private import GITHUB_TOKEN, GITHUB_USERNAME


class GithubConfigError(RuntimeError):
    """Raised when GitHub configuration (token, repo) is missing or invalid."""


def _get_github_token(explicit_token: Optional[str] = None) -> str:
    token = explicit_token or GITHUB_TOKEN
    if not token:
        raise GithubConfigError(
            "GitHub token not found. Set GITHUB_TOKEN or pass explicit_token."
        )
    return token


def get_github_client(token: Optional[str] = None) -> Github:
    """
    Get a PyGithub Github client instance.
    """
    pat = _get_github_token(token)
    return Github(pat)


def _normalize_repo_full_name(repo_full_name: Optional[str]) -> str:
    """
    Ensure we always end up with 'owner/repo'.

    - If repo_full_name is None/empty -> use GITHUB_DEFAULT_REPO (+ username if needed)
    - If repo_full_name has no '/'   -> prepend GITHUB_USERNAME
    - If repo_full_name already has '/' -> use as-is
    """
    base = repo_full_name or GITHUB_DEFAULT_REPO

    if not base:
        raise GithubConfigError(
            "Repository name not provided. "
            "Pass repo_full_name or set GITHUB_DEFAULT_REPO."
        )

    # Already in owner/repo form
    if "/" in base:
        return base

    if not GITHUB_USERNAME:
        raise GithubConfigError(
            "GITHUB_USERNAME must be set when using bare repo names."
        )

    return f"{GITHUB_USERNAME}/{base}"


def get_repo(
    repo_full_name: Optional[str] = None,
    token: Optional[str] = None,
) -> Repository:
    """
    Get a PyGithub Repository instance.
    """
    full_name = _normalize_repo_full_name(repo_full_name)

    gh = get_github_client(token)
    try:
        return gh.get_repo(full_name)
    except Exception as exc:  # noqa: BLE001
        raise GithubConfigError(
            f"Unable to access repository '{full_name}': {exc}"
        ) from exc


def list_directory(
    repo_full_name: Optional[str] = None,
    path: str = "",
    ref: Optional[str] = None,
    token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List files and directories inside a path of a GitHub repository.

    - path "" or "." -> repo root
    - ref:
        * None      -> usa default branch (non passare ref a PyGithub)
        * "main"    -> passa ref="main"
        * commit sha -> idem
    """
    repo = get_repo(repo_full_name, token)

    normalized_path = path.strip("/")
    if normalized_path in ("", "."):
        normalized_path = ""

    # ⚠️ IMPORTANTE: non passare ref=None a PyGithub
    try:
        if ref is None:
            contents = repo.get_contents(normalized_path)
        else:
            contents = repo.get_contents(normalized_path, ref=ref)
    except Exception as exc:  # noqa: BLE001
        raise GithubConfigError(
            f"Error listing directory '{normalized_path}' in repo '{repo.full_name}': {repr(exc)}"
        ) from exc

    if not isinstance(contents, list):
        contents = [contents]

    items: List[Dict[str, Any]] = []
    for item in contents:
        size = getattr(item, "size", None)
        items.append(
            {
                "path": item.path,
                "name": item.name,
                "type": item.type,  # "file" or "dir"
                "size": size,
                "sha": item.sha,
            }
        )

    return items


def get_file_content(
    repo_full_name: Optional[str],
    path: str,
    ref: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve the content of a file in a GitHub repository.
    """
    repo = get_repo(repo_full_name, token)

    normalized_path = path.strip("/")
    if not normalized_path:
        raise FileNotFoundError("Path must not be empty for get_file_content().")

    # ⚠️ Non passare ref=None
    if ref is None:
        obj: ContentFile = repo.get_contents(normalized_path)
    else:
        obj: ContentFile = repo.get_contents(normalized_path, ref=ref)

    if obj.type != "file":
        raise FileNotFoundError(
            f"Path '{normalized_path}' is not a file (type={obj.type})."
        )

    decoded = obj.decoded_content  # bytes

    try:
        text = decoded.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        text = decoded.decode("latin-1", errors="replace")
        encoding = "latin-1"

    return {
        "path": obj.path,
        "name": obj.name,
        "sha": obj.sha,
        "size": getattr(obj, "size", None),
        "encoding": encoding,
        "content": text,
    }


def list_commits(
    repo_full_name: Optional[str] = None,
    path: Optional[str] = None,
    ref: Optional[str] = None,
    token: Optional[str] = None,
    max_commits: int = 50,
) -> List[Dict[str, Any]]:
    """
    List commits in a GitHub repository (optionally filtered by path and ref).

    Parameters
    ----------
    repo_full_name : str | None
        "owner/repo". If None, uses GITHUB_DEFAULT_REPO (+ GITHUB_USERNAME if needed).
    path : str | None
        If provided, only commits touching this file/directory are returned.
        Example: "mcp_servers/mcp_github.py".
    ref : str | None
        Branch name or commit SHA to start from.
        - None -> default branch.
        - "main" -> commits on main.
        - a SHA -> history reachable from that commit.
    token : str | None
        Personal access token. If None, uses GITHUB_TOKEN.
    max_commits : int
        Maximum number of commits to return.

    Returns
    -------
    List[Dict[str, Any]]
        Each item is a JSON-friendly dict with basic commit info.
    """
    repo = get_repo(repo_full_name, token)

    # PyGithub: repo.get_commits(path=..., sha=...)
    kwargs: Dict[str, Any] = {}
    if path:
        # Normalize path similar to other functions
        kwargs["path"] = path.strip("/")
    if ref:
        kwargs["sha"] = ref

    try:
        paginated = repo.get_commits(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise GithubConfigError(
            f"Error getting commits for repo '{repo.full_name}' "
            f"(path={path!r}, ref={ref!r}): {repr(exc)}"
        ) from exc

    commits: List[Dict[str, Any]] = []
    count = 0
    for c in paginated:  # type: ignore[assignment]
        if count >= max_commits:
            break
        # `c` is a github.Commit.Commit
        commit_obj = c.commit  # "raw" commit data
        author = commit_obj.author
        committer = commit_obj.committer

        commits.append(
            {
                "sha": c.sha,
                "message": commit_obj.message,
                "author_name": getattr(author, "name", None),
                "author_email": getattr(author, "email", None),
                "author_date": (
                    getattr(author, "date", None).isoformat()
                    if getattr(author, "date", None)
                    else None
                ),
                "committer_name": getattr(committer, "name", None),
                "committer_email": getattr(committer, "email", None),
                "committer_date": (
                    getattr(committer, "date", None).isoformat()
                    if getattr(committer, "date", None)
                    else None
                ),
                "html_url": getattr(c, "html_url", None),
                "parents": [p.sha for p in getattr(c, "parents", [])],
            }
        )
        count += 1

    return commits
