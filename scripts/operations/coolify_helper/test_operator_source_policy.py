"""Harmless schema and identifier parsing only; no processes, Git or builds.

Run with Python -B. These shapes are synthetic and never attest a real checkout.
"""

import copy
import unittest

import verify_reviewed_source as guard


def schema_fixture():
    source = {name: digit * 40 for name, digit in
              (("head", "1"), ("root_tree", "2"), ("helper_subtree", "3"), ("expected_base", "4"))}
    return {
        "schema_version": 4, "source": source,
        "build_inputs": {name: "a" * 64 for name in guard.BUILD_INPUTS},
        "operator_tools": {name: "b" * 64 for name in guard.OPERATOR_TOOLS},
        "canonical_tar_sha256": "c" * 64,
        "independent_review": {"author_family": "codex", "reviewer_family": "claude", "verdict": "clean",
                               "source": copy.deepcopy(source), "raw_receipt_sha256": "d" * 64},
        "main_review": {"verdict": "clean", "source": copy.deepcopy(source),
                        "findings": {name: {"disposition": "fixed", "evidence": [{"ref": "synthetic-schema-only", "sha256": "e" * 64}]}
                                     for name in guard.FINDINGS}},
        "hosted_ci": {"source": copy.deepcopy(source), "checks": {
            name: {"status": "completed", "conclusion": "success", "head": source["head"], "base": source["expected_base"],
                   "evidence_ref": "synthetic-schema-only", "evidence_sha256": "f" * 64} for name in guard.CHECKS}},
        "all_source_gates_clear": True,
    }


class OperatorSourcePolicyTests(unittest.TestCase):
    def test_schema_four_separates_three_build_inputs_from_six_operator_tools(self):
        self.assertEqual(guard.BUILD_INPUTS, {"Dockerfile", "apply_patch.php", "helper_retry.php"})
        self.assertEqual(guard.OPERATOR_TOOLS, {"verify_reviewed_source.py", "verify_startup_graph.py", "capture_activation_contract.py",
                                               "compose_contract_projection.py", "verify_activation_contract.py", "trusted_operator_loader.py"})
        value = schema_fixture()
        self.assertEqual(guard._validate_manifest(value), value["source"])

    def test_each_executed_operator_tool_is_required(self):
        for name in guard.OPERATOR_TOOLS:
            value = schema_fixture()
            del value["operator_tools"][name]
            with self.subTest(name=name), self.assertRaisesRegex(guard.VerificationError, "invalid_operator_tools"):
                guard._validate_manifest(value)

    def test_operator_tool_map_is_closed_and_each_digest_is_strict(self):
        value = schema_fixture()
        value["operator_tools"]["unlisted_tool.py"] = "b" * 64
        with self.assertRaisesRegex(guard.VerificationError, "invalid_operator_tools"):
            guard._validate_manifest(value)
        for invalid in (True, None, "B" * 64, "b" * 63):
            value = schema_fixture()
            value["operator_tools"]["trusted_operator_loader.py"] = invalid
            with self.subTest(value=invalid), self.assertRaisesRegex(guard.VerificationError, "invalid_operator_tool_digest"):
                guard._validate_manifest(value)

    def test_build_and_operator_hash_maps_are_not_interchangeable(self):
        value = schema_fixture()
        value["build_inputs"], value["operator_tools"] = value["operator_tools"], value["build_inputs"]
        with self.assertRaisesRegex(guard.VerificationError, "invalid_build_inputs"):
            guard._validate_manifest(value)

    def test_executed_tool_binding_matches_exact_manifest(self):
        tools = schema_fixture()["operator_tools"]
        tools["verify_reviewed_source.py"] = "1" * 64
        tools["trusted_operator_loader.py"] = "2" * 64
        guard.validate_executed_tool_binding(tools, "1" * 64, "2" * 64)

    def test_executed_tool_binding_rejects_missing_or_different_manifest_digests(self):
        tools = schema_fixture()["operator_tools"]
        tools["verify_reviewed_source.py"] = "1" * 64
        tools["trusted_operator_loader.py"] = "2" * 64
        for entry_sha, loader_sha, code in (
                (None, "2" * 64, "invalid_executed_entry_digest"),
                ("1" * 64, None, "invalid_executed_loader_digest"),
                ("3" * 64, "2" * 64, "executed_operator_tool_binding_mismatch"),
                ("1" * 64, "4" * 64, "executed_operator_tool_binding_mismatch")):
            with self.subTest(code=code, entry=entry_sha is None), self.assertRaisesRegex(guard.VerificationError, code):
                guard.validate_executed_tool_binding(tools, entry_sha, loader_sha)
        changed = dict(tools)
        changed["verify_reviewed_source.py"] = "3" * 64
        with self.assertRaisesRegex(guard.VerificationError, "executed_operator_tool_binding_mismatch"):
            guard.validate_executed_tool_binding(changed, "1" * 64, "2" * 64)

    def test_new_formal_findings_cannot_be_omitted_or_left_unresolved(self):
        self.assertEqual(len(guard.FINDINGS), 20)
        for name in ("SG-2", "RB-1", "RV366G-RB1-A", "RV366G-RB1-B"):
            value = schema_fixture()
            del value["main_review"]["findings"][name]
            with self.subTest(name=name, state="missing"), self.assertRaisesRegex(guard.VerificationError, "incomplete_main_findings"):
                guard._validate_manifest(value)
            value = schema_fixture()
            value["main_review"]["findings"][name]["disposition"] = "pending"
            with self.subTest(name=name, state="pending"), self.assertRaisesRegex(guard.VerificationError, "main_finding_unresolved"):
                guard._validate_manifest(value)

    def test_previous_or_boolean_schema_version_is_not_schema_four(self):
        for invalid in (3, True):
            value = schema_fixture()
            value["schema_version"] = invalid
            with self.subTest(value=invalid), self.assertRaisesRegex(guard.VerificationError, "unsupported_manifest_version"):
                guard._validate_manifest(value)

    def test_ignored_helper_inventory_is_preserved_and_rejected_with_static_code(self):
        guard._require_no_ignored_helper_files(b"")
        value = b"synthetic/__pycache__/owned.pyc\0"
        with self.assertRaisesRegex(guard.VerificationError, "ignored_helper_files_present") as raised:
            guard._require_no_ignored_helper_files(value)
        self.assertNotIn("owned.pyc", str(raised.exception))

    def test_canonical_iid_parsing_accepts_only_immutable_identifier_text(self):
        value = b"sha256:" + b"1" * 64
        self.assertEqual(guard.parse_built_image_id(value), value.decode())
        self.assertEqual(guard.parse_built_image_id(value + b"\n"), value.decode())
        for invalid in (b"local/coolify-helper-example:test", b"", value + b"\n\n", b" " + value,
                        b"sha256:" + b"A" * 64, value.decode(), None):
            with self.subTest(value=invalid), self.assertRaisesRegex(guard.VerificationError, "invalid_built_image_id"):
                guard.parse_built_image_id(invalid)


if __name__ == "__main__":
    unittest.main()
