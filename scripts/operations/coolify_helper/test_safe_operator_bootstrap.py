"""Harmless constant-module/stdlib isolation and local status-schema checks.

These tests do not call Docker, services, networks, builds, or source-mutation
fixtures. They intentionally remain separate from prior adversarial suites.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import trusted_operator_loader as loader
from capture_activation_contract import OperationFailure, OperationState
from compose_contract_projection import observe_runtime, TESTED_CLIENT, TESTED_SERVER
from verify_activation_contract import _endpoint_ipam


class SafeBootstrapTests(unittest.TestCase):
    def source_buffers(self):
        return {"verify_activation_contract.py": b"VALUE = 7\n",
                "compose_contract_projection.py": b"from verify_activation_contract import VALUE\n",
                "capture_activation_contract.py": b"from compose_contract_projection import VALUE\nRESULT = VALUE\n"}

    def test_hash_mismatch_has_zero_module_execution(self):
        values = {name: b'raise RuntimeError("dummy constant must not execute")\n' for name in loader.DRIVER_FILES}
        expected = {name: hashlib.sha256(value).hexdigest() for name, value in values.items()}
        expected["capture_activation_contract.py"] = "0" * 64
        with self.assertRaises(ValueError):
            loader.load_driver_buffers(values, expected, {name: "/synthetic/" + name for name in values})

    def test_closed_captured_siblings_load_without_changing_search_path(self):
        values = self.source_buffers()
        expected = {name: hashlib.sha256(value).hexdigest() for name, value in values.items()}
        names = [name[:-3] for name in loader.DRIVER_FILES]
        previous = {name: sys.modules.get(name) for name in names}
        search_path = list(sys.path)
        try:
            for name in names:
                sys.modules.pop(name, None)
            module = loader.load_driver_buffers(values, expected, {name: "/synthetic/" + name for name in values})
            self.assertEqual(module.RESULT, 7)
            self.assertEqual(module._TRUSTED_TOOL_SHA256, expected)
            self.assertEqual(sys.path, search_path)
        finally:
            for name, value in previous.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value

    def test_unknown_module_is_rejected_before_execution(self):
        values = {**self.source_buffers(), "unknown.py": b"VALUE = 1\n"}
        expected = {name: hashlib.sha256(value).hexdigest() for name, value in values.items()}
        with self.assertRaises(ValueError):
            loader.load_driver_buffers(values, expected, {name: "/synthetic/" + name for name in values})

    def test_entry_and_loader_pins_must_match_same_manifest(self):
        manifest = {"operator_tools": {name: "a" * 64 for name in loader.OPERATOR_FILES}}
        raw = json.dumps(manifest).encode()
        with patch.object(loader, "_TRUSTED_OPERATOR_ENTRY_SHA256", "a" * 64, create=True):
            loader.operator_binding(raw, hashlib.sha256(raw).hexdigest(), "verify_reviewed_source.py", "a" * 64)
            with self.assertRaises(ValueError):
                loader.operator_binding(raw, hashlib.sha256(raw).hexdigest(), "verify_reviewed_source.py", "b" * 64)
        with patch.object(loader, "_TRUSTED_OPERATOR_ENTRY_SHA256", "b" * 64, create=True):
            with self.assertRaises(ValueError):
                loader.operator_binding(raw, hashlib.sha256(raw).hexdigest(), "verify_reviewed_source.py", "a" * 64)

    def test_isolated_stdlib_ignores_harmless_current_directory_dummies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("json.py", "pathlib.py"):
                (root / name).write_text('raise RuntimeError("harmless dummy module")\n')
            result = subprocess.run([sys.executable, "-I", "-S", "-B", "-c",
                                     'import json,pathlib; print(json.dumps({"stdlib": pathlib.Path("ok").name}))'],
                                    cwd=root, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout), {"stdlib": "ok"})


class SafeStatusAndRuntimeSchemaTests(unittest.TestCase):
    def test_only_empty_requested_ipam_representation_is_equivalent(self):
        self.assertEqual(_endpoint_ipam(None), _endpoint_ipam({}))
        self.assertNotEqual(_endpoint_ipam({"IPv4Address": "192.0.2.10"}), _endpoint_ipam(None))
        for value in ({"unknown": None}, [], "", False):
            with self.subTest(value=value), self.assertRaises(ValueError):
                _endpoint_ipam(value)

    def test_final_persistence_failure_preserves_pre_and_post_success_facts(self):
        for prior in ("pre-mutation", "success"):
            with self.subTest(prior=prior), tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
                operation = OperationState(Path(temporary))
                up = prior == "success"
                operation.update(stage=prior, up_executed=up, up_succeeded=up,
                                 installed_container_id="e" * 64 if up else None,
                                 post_up_inspect_sha256="a" * 64 if up else None)
                with patch.object(operation, "persist", side_effect=OSError("local synthetic status failure")):
                    with self.assertRaises(OperationFailure) as failure:
                        with operation:
                            pass
                value = failure.exception.status
                self.assertEqual(value["stage"], "status-persistence-failed")
                self.assertEqual(value["prior_stage"], prior)
                self.assertTrue(value["failed"])
                self.assertEqual(value["error_class"], "OSError")
                self.assertFalse(value["last_durable_state_current"])
                self.assertEqual(value["up_executed"], up)
                self.assertEqual(value["up_succeeded"], up)
                self.assertFalse(value["automatic_rollback"] or value["automatic_retry"])
                self.assertEqual(json.loads((Path(temporary) / "operation-status.json").read_bytes())["stage"], prior)

    def test_experimental_server_is_rejected_without_any_service_query(self):
        value = {"Client": {**TESTED_CLIENT, "Context": "synthetic", "Experimental": None},
                 "Server": {**TESTED_SERVER, "Experimental": True}}
        with self.assertRaises(ValueError):
            observe_runtime(lambda argv: json.dumps(value).encode())

    def test_unpinned_server_metadata_changes_full_version_digest(self):
        value = {"Client": {**TESTED_CLIENT, "Context": "synthetic", "Experimental": None},
                 "Server": {**TESTED_SERVER, "Experimental": False, "KernelVersion": "synthetic-kernel-a"}}
        first = observe_runtime(lambda argv: json.dumps(value).encode())
        value["Server"]["KernelVersion"] = "synthetic-kernel-b"
        second = observe_runtime(lambda argv: json.dumps(value).encode())
        self.assertNotEqual(first["version_sha256"], second["version_sha256"])
        self.assertEqual(first["server"], second["server"])


if __name__ == "__main__":
    unittest.main()
