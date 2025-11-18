REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"

python "$REPO_ROOT/minimal_mcp_server.py"

