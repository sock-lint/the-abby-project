#!/usr/bin/env bash
# Read-only OAuth smoke check. Set MCP_TOKEN; pass --base-url OR MCP_BASE_URL.
# The default is localhost. Household writes belong in disposable Django tests.
set -euo pipefail
exec python3 "$(dirname "$0")/smoke_mcp.py" "$@"
