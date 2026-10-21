"""Read-only OAuth MCP connection smoke check.

Set MCP_TOKEN to an existing OAuth access token, then run:
    python scripts/smoke_mcp.py --base-url http://127.0.0.1:8000

The check validates initialization, permission-filtered discovery and available
catalog reads. It neither logs in nor creates household/catalog records. The
retired --full mutation script could not restore ledgers, reward opportunities
or notification history; use the disposable Django test suite for write checks.
Tokens and full request/response bodies are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.parse import urlparse

import requests


class MCPClient:
    """Small Streamable HTTP client supporting JSON and SSE responses."""

    def __init__(self, base_url: str, token: str, *, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/mcp"
        self.token = token
        self.session_id: str | None = None
        self.protocol_version = "2025-11-25"
        self._id = 0
        self._session = requests.Session()
        # Authentication must not follow an unreviewed redirect target.
        self._session.trust_env = False

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": self.protocol_version,
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    @staticmethod
    def _parse_body(response: requests.Response) -> dict[str, Any]:
        if "text/event-stream" in response.headers.get("Content-Type", ""):
            candidates = []
            data = []
            for line in response.text.replace("\r\n", "\n").split("\n") + [""]:
                if not line:
                    if data:
                        candidates.append("\n".join(data))
                    data = []
                elif line.startswith("data:"):
                    data.append(line[5:].removeprefix(" "))
            for candidate in reversed(candidates):
                try:
                    result = json.loads(candidate)
                except ValueError:
                    continue
                if isinstance(result, dict) and ("result" in result or "error" in result):
                    return result
            raise RuntimeError("MCP response contained no JSON-RPC result.")
        try:
            result = response.json()
        except ValueError:
            raise RuntimeError("MCP response was not JSON.") from None
        if not isinstance(result, dict):
            raise RuntimeError("MCP response was not an object.")
        return result

    @staticmethod
    def _result(response: dict[str, Any]) -> dict[str, Any]:
        if "error" in response:
            raise RuntimeError("MCP returned a JSON-RPC error.")
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("MCP response had no result object.")
        if result.get("isError"):
            raise RuntimeError("MCP returned a failed tool result.")
        return result

    def rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._id += 1
        try:
            response = self._session.post(
                self.endpoint, headers=self._headers(),
                json={"jsonrpc": "2.0", "id": self._id, "method": method, "params": params},
                timeout=30, allow_redirects=False,
            )
        except requests.RequestException:
            raise RuntimeError("MCP connection failed.") from None
        if response.status_code != 200:
            raise RuntimeError(f"MCP returned HTTP {response.status_code}.")
        parsed = self._parse_body(response)
        if parsed.get("jsonrpc") != "2.0" or parsed.get("id") != self._id:
            raise RuntimeError("MCP response identity did not match the request.")
        self._result(parsed)
        self.session_id = response.headers.get("Mcp-Session-Id") or self.session_id
        return parsed

    def initialize(self) -> dict[str, Any]:
        result = self._result(self.rpc("initialize", {
            "protocolVersion": self.protocol_version, "capabilities": {},
            "clientInfo": {"name": "abby-read-only-smoke", "version": "2.0"},
        }))
        if not isinstance(result.get("protocolVersion"), str) or not isinstance(result.get("capabilities"), dict):
            raise RuntimeError("MCP initialization result was incomplete.")
        self.protocol_version = result["protocolVersion"]
        try:
            response = self._session.post(self.endpoint, headers=self._headers(),
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                timeout=15, allow_redirects=False)
        except requests.RequestException:
            raise RuntimeError("MCP initialization notification failed.") from None
        if response.status_code not in (200, 202, 204):
            raise RuntimeError(f"MCP initialization notification returned HTTP {response.status_code}.")
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        tools = []
        params: dict[str, Any] = {}
        cursors = set()
        for _ in range(100):
            result = self._result(self.rpc("tools/list", params))
            page = result.get("tools")
            if not isinstance(page, list) or any(not isinstance(t, dict) or not isinstance(t.get("name"), str) for t in page):
                raise RuntimeError("MCP tool discovery returned an invalid list.")
            tools.extend(page)
            cursor = result.get("nextCursor")
            if not cursor:
                return tools
            if not isinstance(cursor, str) or cursor in cursors:
                raise RuntimeError("MCP discovery repeated an invalid cursor.")
            cursors.add(cursor)
            params = {"cursor": cursor}
        raise RuntimeError("MCP discovery exceeded its bounded page limit.")

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._result(self.rpc("tools/call", {"name": name, "arguments": {"params": arguments}}))
        payload = result.get("structuredContent")
        if payload is None:
            for block in result.get("content", []):
                if block.get("type") == "text":
                    try:
                        payload = json.loads(block["text"])
                    except (ValueError, KeyError):
                        continue
                    break
        if not isinstance(payload, dict):
            raise RuntimeError("MCP tool returned no structured object.")
        return payload

    def close(self):
        self._session.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("MCP_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--read-only", action="store_true", help="Compatibility option; all checks are read only.")
    parser.add_argument("--full", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.full:
        parser.error("--full was retired; run the Django MCP tests against disposable data.")
    try:
        parsed = urlparse(args.base_url)
        parsed.port
    except ValueError:
        parser.error("--base-url must have a valid host and port.")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        parser.error("--base-url must be an HTTP(S) origin without credentials, path, query or fragment.")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Remote MCP connections require HTTPS.")
    token = os.environ.get("MCP_TOKEN", "").strip()
    if not token:
        parser.error("Set MCP_TOKEN to an existing OAuth access token.")
    client = MCPClient(args.base_url, token)
    try:
        client.initialize()
        tools = {tool["name"] for tool in client.list_tools()}
        checks = 0
        if "get_economy_rules" in tools:
            payload = client.call_tool("get_economy_rules", {})
            if not isinstance(payload.get("schema_version"), int):
                raise RuntimeError("Economy rules response has no schema version.")
            checks += 1
        if "read_rpg_catalog" in tools:
            payload = client.call_tool("read_rpg_catalog", {"section": "categories", "limit": 1})
            if not isinstance(payload.get("results"), list) or not isinstance(payload.get("total"), int):
                raise RuntimeError("Catalog response has no results or total.")
            checks += 1
        sys.stdout.write(f"PASS: initialization; {len(tools)} discoverable tools; {checks} catalog calls verified.\n")
        return 0
    except RuntimeError as exc:
        sys.stderr.write(f"FAIL: {exc}\n")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
