REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"

python "$REPO_ROOT/mcp_servers/mcp_semantic_search.py" --port 9000
