"""Local synthetic HTTP checks for the public MCP smoke client."""
import importlib.util
import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from django.test import SimpleTestCase


spec = importlib.util.spec_from_file_location("abby_mcp_smoke", Path(__file__).resolve().parents[3] / "scripts" / "smoke_mcp.py")
smoke = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = smoke
spec.loader.exec_module(smoke)


class SmokeClientTests(SimpleTestCase):
    def test_oauth_bearer_header(self):
        client = smoke.MCPClient("http://127.0.0.1:8000", "synthetic-token")
        self.assertEqual(client._headers()["Authorization"], "Bearer synthetic-token")

    def test_http_200_tool_error_is_a_failure(self):
        client = smoke.MCPClient("http://127.0.0.1:8000", "synthetic-token")
        with patch.object(client, "rpc", return_value={"jsonrpc":"2.0", "id":1, "result":{"isError":True, "content":[{"type":"text", "text":"synthetic failure"}]}}):
            with self.assertRaises(RuntimeError):
                client.call_tool("get_economy_rules", {})


class SmokeHTTPTests(SimpleTestCase):
    def setUp(self):
        self.requests = []
        self.mode = "success"
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.requests.append((self.headers.get("Authorization"), request))
                method = request["method"]
                if method == "notifications/initialized":
                    self.send_response(202)
                    self.end_headers()
                    return
                if method == "initialize":
                    result = {"protocolVersion":"2025-11-25", "capabilities":{"tools":{}}}
                elif method == "tools/list":
                    names = [] if test.mode == "discovery_only" else ["get_economy_rules", "read_rpg_catalog"]
                    result = {"tools":[{"name":name} for name in names]}
                else:
                    if test.mode == "tool_error":
                        result = {"isError":True, "content":[{"type":"text", "text":"synthetic failure"}]}
                    else:
                        data = {"schema_version":1} if request["params"]["name"] == "get_economy_rules" else {"results":[],"total":0}
                        result = {"content":[], "structuredContent":data}
                payload = {"jsonrpc":"2.0", "id":request["id"], "result":result}
                if test.mode == "rpc_error":
                    payload = {"jsonrpc":"2.0", "id":request["id"], "error":{"code":-1,"message":"synthetic failure"}}
                if test.mode == "wrong_id":
                    payload["id"] = 99999
                body = json.dumps(payload).encode()
                if test.mode == "sse":
                    body = b"event: message\r\ndata: " + body + b"\r\n\r\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream" if test.mode == "sse" else "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_smoke(self):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {"MCP_TOKEN":"synthetic-token"}), redirect_stdout(out), redirect_stderr(err):
            code = smoke.main(["--base-url", f"http://127.0.0.1:{self.server.server_port}"])
        self.assertNotIn("synthetic-token", out.getvalue() + err.getvalue())
        return code, out.getvalue(), err.getvalue()

    def test_json_and_sse_success_validate_real_tool_payloads(self):
        for mode in ("success", "sse"):
            with self.subTest(mode=mode):
                self.mode = mode
                code, out, _ = self.run_smoke()
                self.assertEqual(code, 0)
                self.assertIn("2 catalog calls verified", out)
        for header, request in self.requests:
            self.assertEqual(header, "Bearer synthetic-token")
            if request["method"] == "tools/call":
                self.assertIsInstance(request["params"]["arguments"]["params"], dict)
                self.assertIn(request["params"]["name"], {"get_economy_rules", "read_rpg_catalog"})

    def test_tool_rpc_and_wrong_request_identity_fail(self):
        for mode in ("tool_error", "rpc_error", "wrong_id"):
            with self.subTest(mode=mode):
                self.mode = mode
                code, out, err = self.run_smoke()
                self.assertEqual(code, 1)
                self.assertNotIn("PASS", out)
                self.assertIn("FAIL", err)

    def test_household_grant_only_checks_discovery_and_claims_no_catalog_execution(self):
        self.mode = "discovery_only"
        code, out, _ = self.run_smoke()
        self.assertEqual(code, 0)
        self.assertIn("0 catalog calls verified", out)
        self.assertFalse(any(request["method"] == "tools/call" for _, request in self.requests))
