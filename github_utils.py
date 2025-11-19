"""
Utility functions for interacting with GitHub using PyGithub.

This module is intentionally independent of MCP / FastMCP so it can be
tested and reused easily.
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
