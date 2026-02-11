"""
Contract tests for mcp_servers/mcp_github.py.

These tests mock downstream utility calls, so they do not require
network or GitHub credentials.
"""

import mcp_servers.mcp_github as mod


def _invoke_tool(tool_obj, *args, **kwargs):
    """
    Call a tool regardless of whether FastMCP wrapped it as FunctionTool
    or left it as a plain function.
    """
    if callable(tool_obj):
        return tool_obj(*args, **kwargs)

    for attr in ("fn", "func", "_fn"):
        candidate = getattr(tool_obj, attr, None)
        if callable(candidate):
            return candidate(*args, **kwargs)

    raise TypeError(f"Unsupported tool object: {type(tool_obj)!r}")


def test_list_repo_items_success(monkeypatch):
    expected_items = [{"path": "README.md", "name": "README.md", "type": "file"}]
    monkeypatch.setattr(mod, "list_directory", lambda **kwargs: expected_items)

    out = _invoke_tool(mod.list_repo_items, repo_full_name="owner/repo", path="", ref=None)
    assert out == {"items": expected_items}


def test_list_repo_items_github_config_error(monkeypatch):
    def _raise(**_kwargs):
        raise mod.GithubConfigError("missing token")

    monkeypatch.setattr(mod, "list_directory", _raise)

    out = _invoke_tool(mod.list_repo_items, repo_full_name="owner/repo", path="", ref=None)
    assert "error" in out
    assert "GitHub configuration error" in out["error"]
    assert "missing token" in out["error"]


def test_list_repo_items_invalid_repo_format():
    out = _invoke_tool(mod.list_repo_items, repo_full_name="a/b/c", path="", ref=None)
    assert "error" in out
    assert "owner/repo" in out["error"]


def test_list_repo_items_invalid_ref_with_whitespace():
    out = _invoke_tool(mod.list_repo_items, repo_full_name="owner/repo", path="", ref="main branch")
    assert "error" in out
    assert "must not contain whitespace" in out["error"]


def test_get_file_content_success(monkeypatch):
    expected = {
        "path": "README.md",
        "name": "README.md",
        "sha": "abc123",
        "size": 10,
        "encoding": "utf-8",
        "content": "hello",
    }
    monkeypatch.setattr(mod, "_get_file_content", lambda **kwargs: expected)

    out = _invoke_tool(mod.get_file_content, repo_full_name="owner/repo", path="README.md", ref=None)
    assert out == expected


def test_get_file_content_not_found(monkeypatch):
    def _raise(**_kwargs):
        raise FileNotFoundError("not a file")

    monkeypatch.setattr(mod, "_get_file_content", _raise)

    out = _invoke_tool(mod.get_file_content, repo_full_name="owner/repo", path="README.md", ref=None)
    assert "error" in out
    assert "File not found or not a regular file" in out["error"]
    assert "not a file" in out["error"]


def test_get_file_content_empty_path():
    out = _invoke_tool(mod.get_file_content, repo_full_name="owner/repo", path="   ", ref=None)
    assert "error" in out
    assert "path must be a non-empty string" in out["error"]


def test_get_file_content_github_config_error(monkeypatch):
    def _raise(**_kwargs):
        raise mod.GithubConfigError("repo not accessible")

    monkeypatch.setattr(mod, "_get_file_content", _raise)

    out = _invoke_tool(mod.get_file_content, repo_full_name="owner/repo", path="README.md", ref=None)
    assert "error" in out
    assert "GitHub configuration error" in out["error"]
    assert "repo not accessible" in out["error"]
