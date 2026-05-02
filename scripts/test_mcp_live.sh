#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
# test_mcp_live.sh — Smoke-test the Abby MCP server
#
# Usage:
#   ./scripts/test_mcp_live.sh <TOKEN> [BASE_URL]
#
#   TOKEN    — DRF auth token (grab from Django admin or localStorage)
#   BASE_URL — defaults to https://abby.bos.lol
# ─────────────────────────────────────────────────────────
set -euo pipefail

TOKEN="${1:?Usage: $0 <TOKEN> [BASE_URL]}"
BASE="${2:-https://abby.bos.lol}"
MCP_URL="${BASE}/mcp"

PASS=0
FAIL=0
TOTAL=0

run_test() {
  local name="$1"
  local method="$2"
  local payload="$3"
  local expect_status="${4:-200}"
  TOTAL=$((TOTAL + 1))

  printf "%-45s " "$name"

  response=$(curl -sS -w "\n%{http_code}" \
    -X POST "$MCP_URL" \
    -H "Authorization: Token $TOKEN" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d "$payload" 2>&1) || true

  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | sed '$d')

  if [[ "$http_code" == "$expect_status" ]]; then
    # Check for JSON-RPC error in body
    if echo "$body" | grep -q '"error"'; then
      error_msg=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('error',{}).get('message','unknown'))" 2>/dev/null || echo "parse error")
      printf "⚠️  HTTP %s but RPC error: %s\n" "$http_code" "$error_msg"
      FAIL=$((FAIL + 1))
    else
      printf "✅ HTTP %s\n" "$http_code"
      PASS=$((PASS + 1))
    fi
  else
    printf "❌ HTTP %s (expected %s)\n" "$http_code" "$expect_status"
    FAIL=$((FAIL + 1))
  fi
}

jsonrpc() {
  local method="$1"
  local params="$2"
  local id="${3:-1}"
  echo "{\"jsonrpc\":\"2.0\",\"method\":\"$method\",\"id\":$id,\"params\":$params}"
}

echo "══════════════════════════════════════════════"
echo "  Abby MCP Server — Live Smoke Tests"
echo "  Target: $MCP_URL"
echo "══════════════════════════════════════════════"
echo ""

# ── 0. Health check (no auth needed) ──
printf "%-45s " "[health] GET /health"
TOTAL=$((TOTAL + 1))
health_code=$(curl -sS -o /dev/null -w "%{http_code}" "${BASE}/health" 2>&1 || echo "000")
if [[ "$health_code" == "200" ]]; then
  printf "✅ HTTP %s\n" "$health_code"
  PASS=$((PASS + 1))
else
  printf "❌ HTTP %s\n" "$health_code"
  FAIL=$((FAIL + 1))
fi

# ── 1. MCP Initialize handshake ──
run_test "[init] MCP initialize" "initialize" \
  "$(jsonrpc "initialize" '{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"abby-test","version":"1.0"}}')"

# ── 2. List available tools ──
run_test "[tools] tools/list" "tools/list" \
  "$(jsonrpc "tools/list" '{}' 2)"

# ── 3. Call get_dashboard (no params = own dashboard) ──
run_test "[dashboard] get_dashboard" "tools/call" \
  "$(jsonrpc "tools/call" '{"name":"get_dashboard","arguments":{"params":"{}"}}' 3)"

# ── 4. Call list_children ──
run_test "[users] list_children" "tools/call" \
  "$(jsonrpc "tools/call" '{"name":"list_children","arguments":{"params":"{}"}}' 4)"

# ── 5. Call get_user (self) ──
run_test "[users] get_user (self)" "tools/call" \
  "$(jsonrpc "tools/call" '{"name":"get_user","arguments":{"params":"{}"}}' 5)"

# ── 6. Auth rejection (bad token) ──
printf "%-45s " "[auth] reject bad token"
TOTAL=$((TOTAL + 1))
bad_code=$(curl -sS -o /dev/null -w "%{http_code}" \
  -X POST "$MCP_URL" \
  -H "Authorization: Token badtoken123" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d "$(jsonrpc "initialize" '{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}}' 99)" 2>&1 || echo "000")
if [[ "$bad_code" == "401" ]]; then
  printf "✅ HTTP %s (correctly rejected)\n" "$bad_code"
  PASS=$((PASS + 1))
else
  printf "❌ HTTP %s (expected 401)\n" "$bad_code"
  FAIL=$((FAIL + 1))
fi

# ── Summary ──
echo ""
echo "══════════════════════════════════════════════"
printf "  Results: %d passed, %d failed, %d total\n" "$PASS" "$FAIL" "$TOTAL"
echo "══════════════════════════════════════════════"

[[ $FAIL -eq 0 ]] && exit 0 || exit 1
