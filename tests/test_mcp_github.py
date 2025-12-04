"""
To test the MCP Github...
"""

from mcp_servers.mcp_github import list_repo_items, get_file_content

print("=== Test MCP github tools (direct function calls) ===")

print("\n--- list_repo_items(None, '') ---")
items = list_repo_items(repo_full_name=None, path="")
print("items count:", len(items))
for it in items[:5]:
    print(it)

print("\n--- list_repo_items('mcp-oci-integration', '') ---")
items2 = list_repo_items(repo_full_name="mcp-oci-integration", path="")
print("items2 count:", len(items2))
for it in items2[:5]:
    print(it)

print("\n--- get_file_content(None, 'README.md') ---")
readme = get_file_content(repo_full_name=None, path="README.md")
print("README.md bytes:", len(readme["content"]))
print("README.md encoding:", readme["encoding"])
