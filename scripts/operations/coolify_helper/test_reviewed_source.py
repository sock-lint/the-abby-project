"""Fail-closed operator binding checks using temporary synthetic Git history."""

import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import verify_reviewed_source as guard


class ReviewedSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="coolify-reviewed-source-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.repo = self.directory / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Synthetic Operator")
        self.git("config", "user.email", "operator@example.invalid")
        self.helper = self.repo / guard.HELPER_PATH
        self.helper.mkdir(parents=True)
        (self.repo / "README.md").write_text("synthetic base\n")
        (self.helper / "helper.php").write_text("synthetic base helper\n")
        self.git("add", ".")
        self.git("commit", "-m", "Synthetic base")
        self.base = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.base)
        self.git("checkout", "-b", "synthetic-task")
        (self.helper / "helper.php").write_text("synthetic reviewed helper\n")
        self.git("add", ".")
        self.git("commit", "-m", "Synthetic reviewed source")
        self.source = {
            "head": self.git("rev-parse", "HEAD"),
            "root_tree": self.git("rev-parse", "HEAD^{tree}"),
            "helper_subtree": self.git("rev-parse", f"HEAD:{guard.HELPER_PATH}"),
            "expected_base": self.base,
        }
        self.manifest_path = self.directory / "owner-held-manifest.json"

    def git(self, *args):
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        result = subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "-C", str(self.repo), *args],
            capture_output=True, text=True, check=True, env=env,
        )
        return result.stdout.strip()

    def manifest(self):
        source = copy.deepcopy(self.source)
        return {
            "schema_version": 1,
            "source": source,
            "independent_review": {
                "author_family": "codex", "reviewer_family": "claude", "verdict": "clean",
                "source": copy.deepcopy(source), "raw_receipt_sha256": "a" * 64,
                "owner_held_raw_receipt_path": "/private/owner-held-review.json",
            },
            "main_review": {
                "verdict": "clean", "source": copy.deepcopy(source),
                "findings": {name: {"disposition": "fixed", "evidence": [{"ref": f"owner-held:{name}", "sha256": "b" * 64}]} for name in guard.FINDINGS},
            },
            "hosted_ci": {
                "source": copy.deepcopy(source),
                "checks": {name: {"status": "completed", "conclusion": "success", "head": source["head"], "base": source["expected_base"], "evidence_ref": f"https://example.invalid/hosted/{name}", "evidence_sha256": "c" * 64} for name in guard.CHECKS},
            },
            "all_source_gates_clear": True,
        }

    def write_manifest(self, value=None, payload=None):
        payload = payload if payload is not None else json.dumps(value if value is not None else self.manifest()).encode()
        self.manifest_path.write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()

    def reject(self, value=None, code=None):
        digest = self.write_manifest(value)
        with self.assertRaises(guard.VerificationError) as error:
            guard.verify(self.manifest_path, digest, self.repo)
        if code:
            self.assertEqual(str(error.exception), code)

    def test_exact_external_binding_passes_without_reading_private_receipt(self):
        value = self.manifest()
        value["main_review"]["findings"]["M5"]["disposition"] = "not_applicable"
        digest = self.write_manifest(value)
        result = guard.verify(self.manifest_path, digest, self.repo)
        self.assertTrue(result["verified"])
        self.assertEqual(result["source"], self.source)
        self.assertNotIn("/private", json.dumps(result))
        self.assertNotIn("owner-held:", json.dumps(result))

    def test_wrong_independently_supplied_manifest_digest_rejects(self):
        self.write_manifest()
        with self.assertRaisesRegex(guard.VerificationError, "manifest_digest_mismatch"):
            guard.verify(self.manifest_path, "0" * 64, self.repo)

    def test_each_git_identity_mismatch_rejects(self):
        for field in guard.SOURCE_FIELDS:
            with self.subTest(field=field):
                value = self.manifest()
                replacement = "0" * 40
                value["source"][field] = replacement
                for gate in ["independent_review", "main_review", "hosted_ci"]:
                    value[gate]["source"][field] = replacement
                if field in ("head", "expected_base"):
                    ci_field = "head" if field == "head" else "base"
                    for check in value["hosted_ci"]["checks"].values():
                        check[ci_field] = replacement
                self.reject(value, f"git_{field}_mismatch")

    def test_moved_origin_main_rejects_even_when_base_remains_ancestor(self):
        self.git("update-ref", "refs/remotes/origin/main", self.source["head"])
        self.reject(code="git_expected_base_mismatch")

    def test_new_clean_commit_cannot_reuse_the_previous_review(self):
        (self.helper / "helper.php").write_text("unreviewed follow-up commit\n")
        self.git("add", ".")
        self.git("commit", "-m", "Synthetic unreviewed follow-up")
        self.reject()

    def test_nonancestor_base_rejects_even_with_matching_ref_and_attestations(self):
        unrelated = self.git("commit-tree", self.source["root_tree"], "-m", "Synthetic unrelated root")
        self.git("update-ref", "refs/remotes/origin/main", unrelated)
        self.source["expected_base"] = unrelated
        self.reject(code="base_not_ancestor")

    def test_dirty_tracked_and_staged_changes_reject(self):
        tracked = self.repo / "README.md"
        tracked.write_text("unreviewed tracked edit\n")
        self.reject(code="checkout_not_clean")
        self.git("add", "README.md")
        self.reject(code="checkout_not_clean")

    def test_untracked_helper_source_rejects(self):
        (self.helper / "unreviewed.php").write_text("unreviewed source\n")
        self.reject(code="checkout_not_clean")

    def test_review_must_be_clean_independent_and_bound_to_exact_source(self):
        for field, replacement, code in [
            ("verdict", "pending", "independent_review_not_clean"),
            ("reviewer_family", "codex", "independent_review_not_clean"),
            ("author_family", "claude", "independent_review_not_clean"),
            ("raw_receipt_sha256", "not-a-digest", "invalid_raw_review_digest"),
        ]:
            with self.subTest(field=field):
                value = self.manifest()
                value["independent_review"][field] = replacement
                self.reject(value, code)
        value = self.manifest()
        value["independent_review"]["source"]["head"] = self.base
        self.reject(value, "independent_review_source_mismatch")

    def test_every_main_finding_requires_final_disposition_and_evidence(self):
        for name in guard.FINDINGS:
            for mutation, code in [("pending", "main_finding_unresolved"), ("no_evidence", "main_finding_evidence_missing")]:
                with self.subTest(finding=name, mutation=mutation):
                    value = self.manifest()
                    if mutation == "pending":
                        value["main_review"]["findings"][name]["disposition"] = "pending"
                    else:
                        value["main_review"]["findings"][name]["evidence"] = []
                    self.reject(value, code)
        value = self.manifest()
        del value["main_review"]["findings"]["H1"]
        self.reject(value, "incomplete_main_findings")
        value = self.manifest()
        value["main_review"]["findings"]["H1"]["evidence"][0]["sha256"] = "invalid"
        self.reject(value, "invalid_main_finding_evidence")

    def test_main_verdict_and_source_must_match(self):
        value = self.manifest()
        value["main_review"]["verdict"] = "changes_requested"
        self.reject(value, "main_review_not_clean")
        value = self.manifest()
        value["main_review"]["source"]["root_tree"] = "0" * 40
        self.reject(value, "main_review_source_mismatch")

    def test_each_required_hosted_check_must_succeed_on_exact_head_and_base(self):
        for name in guard.CHECKS:
            for field, replacement, code in [
                ("status", "in_progress", "hosted_ci_not_successful"),
                ("conclusion", "failure", "hosted_ci_not_successful"),
                ("conclusion", "skipped", "hosted_ci_not_successful"),
                ("head", self.base, "hosted_ci_head_base_mismatch"),
                ("base", self.source["head"], "hosted_ci_head_base_mismatch"),
                ("evidence_sha256", "invalid", "invalid_hosted_ci_evidence"),
            ]:
                with self.subTest(check=name, field=field):
                    value = self.manifest()
                    value["hosted_ci"]["checks"][name][field] = replacement
                    self.reject(value, code)
        value = self.manifest()
        del value["hosted_ci"]["checks"]["API fixtures"]
        self.reject(value, "incomplete_hosted_ci")

    def test_matching_git_alone_cannot_approve_uncleared_gates(self):
        value = self.manifest()
        value["all_source_gates_clear"] = False
        self.reject(value, "source_gates_not_clear")

    def test_duplicate_unknown_and_malformed_schema_fields_reject(self):
        payload = json.dumps(self.manifest()).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1', 1).encode()
        digest = self.write_manifest(payload=payload)
        with self.assertRaisesRegex(guard.VerificationError, "duplicate_manifest_key"):
            guard.verify(self.manifest_path, digest, self.repo)
        value = self.manifest()
        value["invented_raw_claude_schema"] = {}
        self.reject(value, "invalid_manifest_schema")
        value = self.manifest()
        value["schema_version"] = True
        self.reject(value, "unsupported_manifest_version")

    def test_cli_emits_static_failure_without_echoing_private_values(self):
        value = self.manifest()
        private_marker = "PRIVATE-REVIEW-PAYLOAD-MUST-NOT-APPEAR"
        value["independent_review"]["reviewer_family"] = private_marker
        digest = self.write_manifest(value)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(guard, "CHECKOUT_ROOT", self.repo), redirect_stdout(out), redirect_stderr(err):
            status = guard.main(["--manifest", str(self.manifest_path), "--expected-manifest-sha256", digest])
        self.assertEqual(status, 1)
        self.assertFalse(json.loads(out.getvalue())["verified"])
        self.assertNotIn(private_marker, out.getvalue() + err.getvalue())
        self.assertNotIn(str(self.manifest_path), out.getvalue() + err.getvalue())

    def test_cli_requires_external_manifest_and_digest(self):
        out = io.StringIO()
        with redirect_stdout(out):
            status = guard.main([])
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(out.getvalue())["error"], "invalid_arguments")


if __name__ == "__main__":
    unittest.main()
