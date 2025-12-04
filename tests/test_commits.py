"""
Simple test script for list_commits() from github_util.py.

Run with:
    python test_commits.py
"""

from pprint import pprint
from github_utils import list_commits


def main():
    print("\n=== Test: Last 10 commits on default branch ===\n")
    commits = list_commits(max_commits=10)
    pprint(commits)
    print("")

    print("\n=== Test: Commits touching a specific file (if exists) ===\n")
    try:
        commits_file = list_commits(
            path="mcp_servers/mcp_github.py",
            max_commits=5,
        )
        pprint(commits_file)
    except Exception as exc:
        print(f"Error when listing commits for file: {exc}")
    print("")

    print("\n=== Test: Commits on a specific branch (main) ===\n")
    try:
        commits_main = list_commits(ref="main", max_commits=5)
        pprint(commits_main)
    except Exception as exc:
        print(f"Error when listing commits on main: {exc}")


if __name__ == "__main__":
    main()
