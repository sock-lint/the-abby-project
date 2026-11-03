"""Fail-closed operator binding checks using temporary synthetic Git history."""

import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import ANY, patch

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
        for name in guard.BUILD_INPUTS | guard.OPERATOR_TOOLS:
            (self.helper / name).write_text(f"synthetic reviewed {name}\n")
        (self.helper / "nested").mkdir()
        executable = self.helper / "nested" / "checked.sh"
        executable.write_text("#!/bin/sh\nexit 0\n")
        executable.chmod(0o755)
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
        self.export = self.directory / "operator-context"
        trusted_markers = patch.multiple(
            guard, create=True,
            _TRUSTED_OPERATOR_ENTRY_SHA256=hashlib.sha256((self.helper / "verify_reviewed_source.py").read_bytes()).hexdigest(),
            _TRUSTED_OPERATOR_LOADER_SHA256=hashlib.sha256((self.helper / "trusted_operator_loader.py").read_bytes()).hexdigest(),
        )
        trusted_markers.start()
        self.addCleanup(trusted_markers.stop)

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
            "schema_version": 4,
            "source": source,
            "build_inputs": {name: hashlib.sha256((self.helper / name).read_bytes()).hexdigest() for name in guard.BUILD_INPUTS},
            "operator_tools": {name: hashlib.sha256((self.helper / name).read_bytes()).hexdigest() for name in guard.OPERATOR_TOOLS},
            "canonical_tar_sha256": hashlib.sha256(self.fixture_tar()).hexdigest(),
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

    def fixture_tar(self, mutation=None):
        """Owner-side fixture TAR, built independently of guard functions."""
        entries = []
        for path in sorted(self.helper.rglob("*")):
            member = tarfile.TarInfo(path.relative_to(self.helper).as_posix())
            member.uid = member.gid = member.mtime = 0
            member.uname = member.gname = ""
            if path.is_dir():
                member.type, member.mode, payload = tarfile.DIRTYPE, 0o755, None
            else:
                payload = path.read_bytes()
                member.mode = 0o755 if path.stat().st_mode & 0o100 else 0o644
                member.size = len(payload)
            entries.append((member, payload))
        if mutation:
            mutation(entries)
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for member, payload in entries:
                archive.addfile(member, io.BytesIO(payload) if payload is not None else None)
        return stream.getvalue()

    def write_manifest(self, value=None, payload=None):
        payload = payload if payload is not None else json.dumps(value if value is not None else self.manifest()).encode()
        self.manifest_path.write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()

    def reject(self, value=None, code=None):
        digest = self.write_manifest(value)
        with self.assertRaises(guard.VerificationError) as error:
            guard.verify(self.manifest_path, digest, self.repo, export_context=self.export)
        if code:
            self.assertEqual(str(error.exception), code)

    def test_exact_external_binding_passes_without_reading_private_receipt(self):
        value = self.manifest()
        value["main_review"]["findings"]["M5"]["disposition"] = "not_applicable"
        digest = self.write_manifest(value)
        with patch.object(guard, "_docker") as docker:
            result = guard.verify(self.manifest_path, digest, self.repo, export_context=self.export)
        docker.assert_not_called()
        self.assertTrue(result["verified"])
        self.assertEqual(result["source"], self.source)
        self.assertNotIn("/private", json.dumps(result))
        self.assertNotIn("owner-held:", json.dumps(result))
        self.assertTrue(result["exported_context_verified"])
        self.assertTrue(result["canonical_tar_verified"])
        self.assertEqual(result["canonical_tar_sha256"], value["canonical_tar_sha256"])
        self.assertFalse(result["candidate_build_completed"])
        self.assertFalse(result["image_patch_receipt_verified"])
        self.assertEqual(result["expected_image_patch_receipt"], {
            "patcher_sha256": value["build_inputs"]["apply_patch.php"],
            "retry_source_sha256": value["build_inputs"]["helper_retry.php"],
        })
        for name in guard.BUILD_INPUTS:
            self.assertEqual((self.export / name).read_bytes(), (self.helper / name).read_bytes())
        self.assertEqual((self.export / "nested" / "checked.sh").stat().st_mode & 0o777, 0o755)

    def test_wrong_independently_supplied_manifest_digest_rejects(self):
        self.write_manifest()
        with self.assertRaisesRegex(guard.VerificationError, "manifest_digest_mismatch"):
            guard.verify(self.manifest_path, "0" * 64, self.repo, export_context=self.export)

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
        self.assertEqual(guard.FINDINGS, {"H1", "H2", "M1", "M2", "M3", "M4", "M5",
                                         "RV366D-ACT-1", "RV366D-ACT-2", "SG-1", "RV366D-README-1", "N1", "N2", "N3", "N4", "N5", "SG-2", "RB-1",
                                         "RV366G-RB1-A", "RV366G-RB1-B"})
        for name in guard.FINDINGS:
            for mutation, code in [("pending", "main_finding_unresolved"), ("no_evidence", "main_finding_evidence_missing")]:
                with self.subTest(finding=name, mutation=mutation):
                    value = self.manifest()
                    if mutation == "pending":
                        value["main_review"]["findings"][name]["disposition"] = "pending"
                    else:
                        value["main_review"]["findings"][name]["evidence"] = []
                    self.reject(value, code)
        for name in guard.FINDINGS:
            with self.subTest(missing=name):
                value = self.manifest()
                del value["main_review"]["findings"][name]
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
        payload = json.dumps(self.manifest()).replace('"schema_version": 4', '"schema_version": 4, "schema_version": 4', 1).encode()
        digest = self.write_manifest(payload=payload)
        with self.assertRaisesRegex(guard.VerificationError, "duplicate_manifest_key"):
            guard.verify(self.manifest_path, digest, self.repo, export_context=self.export)
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
        with patch.object(guard, "CHECKOUT_ROOT", self.repo), patch.object(guard, "_trusted_operator_entry"), redirect_stdout(out), redirect_stderr(err):
            status = guard.main(["--manifest", str(self.manifest_path), "--expected-manifest-sha256", digest, "--export-context", str(self.export)])
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

    def test_cli_requires_export_in_the_same_verification_process(self):
        digest = self.write_manifest()
        out = io.StringIO()
        with redirect_stdout(out):
            status = guard.main(["--manifest", str(self.manifest_path), "--expected-manifest-sha256", digest])
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(out.getvalue())["error"], "invalid_arguments")

    def test_replacement_refs_for_blob_and_tree_are_rejected(self):
        for name in ("Dockerfile", None):
            with self.subTest(kind="blob" if name else "tree"):
                original = self.git("rev-parse", f"HEAD:{guard.HELPER_PATH}/{name}") if name else self.source["helper_subtree"]
                replacement = self.git("rev-parse", f"HEAD:{guard.HELPER_PATH}/helper.php") if name else self.source["root_tree"]
                self.git("replace", original, replacement)
                self.reject(code="git_replacement_refs")
                self.git("replace", "-d", original)
        self.assertFalse(self.export.exists())

    def test_packed_replacement_refs_are_rejected(self):
        self.git("replace", self.source["helper_subtree"], self.source["root_tree"])
        self.git("pack-refs", "--all")
        self.reject(code="git_replacement_refs")

    def test_inherited_replacement_configuration_is_rejected(self):
        for name in ("GIT_REPLACE_REF_BASE", "GIT_NO_REPLACE_OBJECTS", "GIT_GRAFT_FILE"):
            with self.subTest(name=name), patch.dict(os.environ, {name: "synthetic"}):
                self.reject(code="git_replacement_environment")

    def test_info_attributes_filters_and_export_ignore_are_rejected(self):
        path = Path(self.git("rev-parse", "--git-path", "info/attributes"))
        if not path.is_absolute():
            path = self.repo / path
        for content in ("Dockerfile export-ignore\n", "* filter=malicious\n"):
            with self.subTest(content=content):
                path.write_text(content)
                self.reject(code="unsafe_git_info_file")
        self.assertFalse(self.export.exists())

    def test_local_filters_includes_and_unsafe_query_configuration_reject(self):
        for key, value in (("filter.synthetic.clean", "false"), ("filter.synthetic.smudge", "false"),
                           ("filter.synthetic.process", "false"), ("core.attributesFile", "/private/attributes"),
                           ("core.fsmonitor", "false"), ("core.useReplaceRefs", "false"),
                           ("include.path", "/private/unused"), ("extensions.worktreeConfig", "true")):
            with self.subTest(key=key):
                self.git("config", key, value)
                self.reject(code="unsafe_git_local_config")
                self.git("config", "--unset", key)
        self.assertFalse(self.export.exists())

    def test_global_attributes_and_filters_cannot_affect_raw_export(self):
        attrs = self.directory / "global-attributes"
        attrs.write_text("* export-ignore filter=malicious\n")
        config = self.directory / "global-gitconfig"
        marker = self.directory / "FILTER-MUST-NOT-RUN"
        config.write_text(f"[core]\n attributesFile = {attrs}\n[filter \"malicious\"]\n clean = touch {marker}\n smudge = touch {marker}\n")
        digest = self.write_manifest()
        with patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config)}):
            result = guard.verify(self.manifest_path, digest, self.repo, export_context=self.export)
        self.assertTrue(result["verified"])
        self.assertFalse(marker.exists())
        self.assertTrue((self.export / "Dockerfile").is_file())

    def test_tracked_export_attributes_are_ignored_by_raw_export(self):
        (self.helper / ".gitattributes").write_text("Dockerfile export-ignore\nhelper_retry.php export-subst\n")
        self.git("add", ".")
        self.git("commit", "-m", "Synthetic reviewed archive attributes")
        self.source.update(head=self.git("rev-parse", "HEAD"), root_tree=self.git("rev-parse", "HEAD^{tree}"),
                           helper_subtree=self.git("rev-parse", f"HEAD:{guard.HELPER_PATH}"))
        digest = self.write_manifest()
        guard.verify(self.manifest_path, digest, self.repo, export_context=self.export)
        self.assertEqual((self.export / "Dockerfile").read_bytes(), (self.helper / "Dockerfile").read_bytes())

    def test_build_input_hash_missing_wrong_or_extra_rejects(self):
        value = self.manifest()
        del value["build_inputs"]["Dockerfile"]
        self.reject(value, "invalid_build_inputs")
        value = self.manifest()
        value["build_inputs"]["invented.php"] = "a" * 64
        self.reject(value, "invalid_build_inputs")
        for name in guard.BUILD_INPUTS:
            with self.subTest(name=name):
                value = self.manifest()
                value["build_inputs"][name] = "0" * 64
                self.reject(value, "export_build_input_mismatch")
                self.assertFalse(self.export.exists())

    def test_fresh_export_is_required_and_existing_output_is_preserved(self):
        self.export.mkdir()
        marker = self.export / "existing-owner-file"
        marker.write_text("preserve this file\n")
        self.reject(code="export_context_not_fresh")
        self.assertEqual(marker.read_text(), "preserve this file\n")

    def test_export_cannot_be_inside_checkout(self):
        digest = self.write_manifest()
        with self.assertRaisesRegex(guard.VerificationError, "export_context_inside_checkout"):
            guard.verify(self.manifest_path, digest, self.repo, export_context=self.repo / "unsafe-export")

    def test_independent_export_validation_detects_bytes_modes_and_extra_files(self):
        value = self.manifest()
        digest = self.write_manifest(value)
        guard.verify(self.manifest_path, digest, self.repo, export_context=self.export)
        original = (self.export / "Dockerfile").read_bytes()
        for mutation in ("bytes", "mode", "extra", "symlink"):
            with self.subTest(mutation=mutation):
                path = self.export / "Dockerfile"
                if mutation == "bytes":
                    path.write_bytes(b"unreviewed context bytes\n")
                elif mutation == "mode":
                    path.chmod(0o755)
                elif mutation == "extra":
                    (self.export / "unreviewed.txt").write_text("unreviewed\n")
                else:
                    path.unlink()
                    path.symlink_to(self.helper / "Dockerfile")
                with self.assertRaises(guard.VerificationError):
                    guard.verify_exported_context(self.export, self.source["helper_subtree"], value["build_inputs"], value["operator_tools"])
                if path.is_symlink():
                    path.unlink()
                path.write_bytes(original)
                path.chmod(0o644)
                (self.export / "unreviewed.txt").unlink(missing_ok=True)

    def test_tampering_during_export_is_rejected_and_partial_context_removed(self):
        digest = self.write_manifest()
        real_check = guard.verify_exported_context

        def tampered_check(directory, tree, inputs, tools):
            (Path(directory) / "apply_patch.php").write_text("unreviewed injected payload\n")
            return real_check(directory, tree, inputs, tools)

        with patch.object(guard, "verify_exported_context", side_effect=tampered_check):
            with self.assertRaisesRegex(guard.VerificationError, "export_context_tree_mismatch"):
                guard.verify(self.manifest_path, digest, self.repo, export_context=self.export)
        self.assertFalse(self.export.exists())

    def test_ref_moving_during_export_invalidates_and_removes_context(self):
        digest = self.write_manifest()
        real_check = guard.verify_exported_context

        def moved_ref_check(directory, tree, inputs, tools):
            real_check(directory, tree, inputs, tools)
            self.git("update-ref", "refs/remotes/origin/main", self.source["head"])

        with patch.object(guard, "verify_exported_context", side_effect=moved_ref_check):
            with self.assertRaisesRegex(guard.VerificationError, "checkout_changed_during_export"):
                guard.verify(self.manifest_path, digest, self.repo, export_context=self.export)
        self.assertFalse(self.export.exists())

    def test_raw_tree_symlinks_and_gitlinks_are_rejected(self):
        for mode in ("120000", "160000"):
            with self.subTest(mode=mode):
                oid = self.source["head"] if mode == "160000" else self.git("rev-parse", f"HEAD:{guard.HELPER_PATH}/helper.php")
                self.git("update-index", "--add", "--cacheinfo", f"{mode},{oid},{guard.HELPER_PATH}/unsafe-entry")
                self.git("commit", "-m", "Synthetic unsafe reviewed tree entry")
                self.source.update(head=self.git("rev-parse", "HEAD"), root_tree=self.git("rev-parse", "HEAD^{tree}"),
                                   helper_subtree=self.git("rev-parse", f"HEAD:{guard.HELPER_PATH}"))
                # The fixture intentionally lacks a matching worktree entry;
                # bypass only cleanliness to reach the independent exporter.
                with self.assertRaisesRegex(guard.VerificationError, "unsafe_context_tree_entry"):
                    guard._export_context(self.repo, self.source, self.manifest()["build_inputs"], self.export, self.manifest()["operator_tools"])
                self.git("reset", "--hard", "HEAD~1")

    def test_assume_unchanged_and_skip_worktree_cannot_hide_dirty_files(self):
        for flag, reset in (("--assume-unchanged", "--no-assume-unchanged"), ("--skip-worktree", "--no-skip-worktree")):
            with self.subTest(flag=flag):
                self.git("update-index", flag, "README.md")
                (self.repo / "README.md").write_text("hidden dirty edit\n")
                self.reject(code="unsafe_git_index_flags")
                self.git("update-index", reset, "README.md")
                self.git("checkout", "--", "README.md")

    def test_canonical_tar_digest_requires_an_independent_manifest_binding(self):
        value = self.manifest()
        del value["canonical_tar_sha256"]
        self.reject(value, "invalid_manifest_schema")
        value = self.manifest()
        value["canonical_tar_sha256"] = "invalid"
        self.reject(value, "invalid_canonical_tar_digest")
        value["canonical_tar_sha256"] = "0" * 64
        with patch.object(guard, "_docker") as docker:
            self.reject(value, "canonical_tar_digest_mismatch")
        docker.assert_not_called()
        self.assertFalse(self.export.exists())

    def test_binary_payload_survives_raw_export_tar_and_inventory_verification(self):
        payload = b"\x00\xff\xfe\n\r\x80binary\x00"
        (self.helper / "binary.dat").write_bytes(payload)
        self.git("add", ".")
        self.git("commit", "-m", "Synthetic reviewed binary source")
        self.source.update(head=self.git("rev-parse", "HEAD"), root_tree=self.git("rev-parse", "HEAD^{tree}"),
                           helper_subtree=self.git("rev-parse", f"HEAD:{guard.HELPER_PATH}"))
        value = self.manifest()
        digest = self.write_manifest(value)
        result = guard.verify(self.manifest_path, digest, self.repo, export_context=self.export)
        captured = guard._capture_canonical_tar(self.export)
        guard.verify_canonical_tar(captured, self.source["helper_subtree"], value["build_inputs"], value["operator_tools"])
        self.assertEqual(hashlib.sha256(captured).hexdigest(), result["canonical_tar_sha256"])
        with tarfile.open(fileobj=io.BytesIO(captured), mode="r:") as archive:
            self.assertEqual(archive.extractfile("binary.dat").read(), payload)

    def test_canonical_tar_sorts_directories_and_normalizes_owner_exec_modes(self):
        digest = self.write_manifest()
        guard.verify(self.manifest_path, digest, self.repo, export_context=self.export)
        captured = guard._capture_canonical_tar(self.export)
        with tarfile.open(fileobj=io.BytesIO(captured), mode="r:") as archive:
            members = archive.getmembers()
            self.assertEqual([item.name for item in members], sorted(item.name for item in members))
            for item in members:
                self.assertEqual((item.uid, item.gid, item.mtime, item.uname, item.gname), (0, 0, 0, "", ""))
                self.assertEqual(item.mode, 0o755 if item.isdir() or item.name == "nested/checked.sh" else 0o644)
        # Group/other execution bits cannot change Git's owner-exec meaning or
        # enter a canonical archive as an unreviewed filesystem mode.
        (self.export / "Dockerfile").chmod(0o654)
        with self.assertRaisesRegex(guard.VerificationError, "export_context_unsafe_mode"):
            guard._capture_canonical_tar(self.export)

    def test_tar_inventory_rejects_content_mode_tree_and_input_digest_changes(self):
        value = self.manifest()
        payload = self.fixture_tar()
        guard.verify_canonical_tar(payload, self.source["helper_subtree"], value["build_inputs"], value["operator_tools"])
        with self.assertRaisesRegex(guard.VerificationError, "tar_context_tree_mismatch"):
            guard.verify_canonical_tar(payload, "0" * 40, value["build_inputs"], value["operator_tools"])
        changed_inputs = dict(value["build_inputs"], Dockerfile="0" * 64)
        with self.assertRaisesRegex(guard.VerificationError, "tar_build_input_mismatch"):
            guard.verify_canonical_tar(payload, self.source["helper_subtree"], changed_inputs, value["operator_tools"])

        def change_content(entries):
            member, data = entries[0]
            entries[0] = (member, bytes([data[0] ^ 1]) + data[1:])

        def change_mode(entries):
            entries[0][0].mode = 0o755

        for mutate in (change_content, change_mode):
            with self.subTest(mutation=mutate.__name__):
                with self.assertRaisesRegex(guard.VerificationError, "tar_context_tree_mismatch"):
                    guard.verify_canonical_tar(self.fixture_tar(mutate), self.source["helper_subtree"], value["build_inputs"], value["operator_tools"])

    def test_tar_rejects_duplicate_fifo_symlink_hardlink_and_unsafe_names(self):
        value = self.manifest()
        for kind in ("duplicate", "fifo", "symlink", "hardlink", "newline", "traversal", "absolute"):
            def mutate(entries):
                member = tarfile.TarInfo("unsafe")
                if kind == "duplicate":
                    member = copy.copy(entries[0][0])
                    entries.append((member, entries[0][1]))
                    return
                member.mode = 0o644
                member.type = {"fifo": tarfile.FIFOTYPE, "symlink": tarfile.SYMTYPE,
                               "hardlink": tarfile.LNKTYPE}.get(kind, tarfile.REGTYPE)
                member.name = {"newline": "unsafe\nname", "traversal": "../unsafe", "absolute": "/unsafe"}.get(kind, "unsafe")
                if kind in ("symlink", "hardlink"):
                    member.linkname = "Dockerfile"
                entries.append((member, b"" if member.isreg() else None))
            with self.subTest(kind=kind), self.assertRaises(guard.VerificationError):
                guard.verify_canonical_tar(self.fixture_tar(mutate), self.source["helper_subtree"], value["build_inputs"], value["operator_tools"])

    def test_tar_metadata_order_and_trailing_bytes_are_not_canonical(self):
        value = self.manifest()
        for kind in ("uid", "mtime", "order", "trailing"):
            def mutate(entries):
                if kind == "uid":
                    entries[0][0].uid = 1234
                elif kind == "mtime":
                    entries[0][0].mtime = 1234
                elif kind == "order":
                    entries.reverse()
            payload = self.fixture_tar(mutate)
            if kind == "trailing":
                payload += b"unreviewed trailing bytes"
            with self.subTest(kind=kind), self.assertRaises(guard.VerificationError):
                guard.verify_canonical_tar(payload, self.source["helper_subtree"], value["build_inputs"], value["operator_tools"])

    def test_all_raw_paths_and_collisions_are_rejected_before_any_export_write(self):
        oid = self.git("rev-parse", f"HEAD:{guard.HELPER_PATH}/Dockerfile")
        for name in ("bad\nname", "../bad", "/bad", ".git/config", "nested/../../bad", "Dockerfile", "Dockerfile/child", "x" * 100):
            records = f"100644 blob {oid}\tDockerfile\0".encode() + f"100644 blob {oid}\t{name}\0".encode()
            result = subprocess.CompletedProcess([], 0, stdout=records)
            with self.subTest(name=name), patch.object(guard, "_git", return_value=result) as query:
                with self.assertRaises(guard.VerificationError):
                    guard._export_context(self.repo, self.source, self.manifest()["build_inputs"], self.export, self.manifest()["operator_tools"])
                self.assertFalse(self.export.exists())
                self.assertEqual(query.call_count, 1)

    def test_capture_rejects_filesystem_fifo_and_symlink_without_reading_them(self):
        self.export.mkdir()
        unsafe = self.export / "unsafe"
        for kind in ("fifo", "symlink"):
            if kind == "fifo":
                os.mkfifo(unsafe)
            else:
                unsafe.symlink_to(self.helper / "Dockerfile")
            with self.subTest(kind=kind), self.assertRaisesRegex(guard.VerificationError, "export_context_unsafe_mode"):
                guard._capture_canonical_tar(self.export)
            unsafe.unlink()

    def test_docker_build_consumes_same_captured_bytes_after_diagnostic_context_changes(self):
        value = self.manifest()
        digest = self.write_manifest(value)
        captured, calls = [], []
        original_capture = guard._capture_canonical_tar

        def capture_then_mutate(directory):
            payload = original_capture(directory)
            captured.append(payload)
            (Path(directory) / "Dockerfile").write_text("UNREVIEWED AFTER CAPTURE\n")
            return payload

        def docker(args, payload=None):
            calls.append((args, payload))
            if args[0] == "build":
                self.assertIs(payload, captured[0])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), value["canonical_tar_sha256"])
                with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
                    self.assertEqual(archive.extractfile("Dockerfile").read(), (self.helper / "Dockerfile").read_bytes())
            return subprocess.CompletedProcess(args, 0, stdout=b"")

        tag = "local/coolify-helper-synthetic:unique-123"
        built_id = "sha256:" + "e" * 64
        with patch.object(guard, "_capture_canonical_tar", side_effect=capture_then_mutate), patch.object(guard, "_docker", side_effect=docker), \
                patch.object(guard, "_capture_built_image_id", return_value=built_id):
            result = guard.verify(self.manifest_path, digest, self.repo, export_context=self.export, build_candidate_tag=tag)
        self.assertTrue(result["candidate_build_completed"])
        self.assertEqual(result["built_image_id"], built_id)
        self.assertEqual(calls[0][0], ["image", "ls", "--quiet", "--no-trunc", "--filter", "reference=" + tag])
        self.assertEqual(calls[1][0], ["build", "--network=none", "--pull=false", "--iidfile", ANY, "--label",
                                      "lol.bos.coolify-helper-patch.source-commit=" + self.source["head"], "--tag", tag, "-"])

    def test_candidate_tag_rejects_existing_images_and_daemon_errors_without_build(self):
        tag = "local/coolify-helper-synthetic:unique-123"
        with patch.object(guard, "_docker", return_value=subprocess.CompletedProcess([], 0, stdout=b"synthetic-image-id\n")) as docker:
            with self.assertRaisesRegex(guard.VerificationError, "candidate_tag_already_exists"):
                guard._build_candidate(tag, b"unused", self.source["head"])
            self.assertEqual(docker.call_count, 1)
        with patch.object(guard, "_docker", side_effect=guard.VerificationError("candidate_build_unavailable")) as docker:
            with self.assertRaisesRegex(guard.VerificationError, "candidate_build_unavailable"):
                guard._build_candidate(tag, b"unused", self.source["head"])
            self.assertEqual(docker.call_count, 1)

    def test_candidate_tags_are_strict_and_rejected_before_export_or_docker(self):
        digest = self.write_manifest()
        for tag in ("latest", "ghcr.io/coolify:latest", "local/coolify-helper-synthetic", "local/other:tag", "local/coolify-helper-synthetic:tag\n", "local/coolify-helper-synthetic:tag;false"):
            with self.subTest(tag=tag), patch.object(guard, "_docker") as docker:
                with self.assertRaisesRegex(guard.VerificationError, "invalid_candidate_tag"):
                    guard.verify(self.manifest_path, digest, self.repo, export_context=self.export, build_candidate_tag=tag)
                self.assertFalse(self.export.exists())
                docker.assert_not_called()
        with patch.object(guard, "_docker") as docker:
            with self.assertRaisesRegex(guard.VerificationError, "invalid_candidate_source_head"):
                guard._build_candidate("local/coolify-helper-synthetic:unique-123", b"unused", "unverified")
            docker.assert_not_called()

    def test_docker_subprocess_receives_binary_stdin_without_a_mutable_tar_path(self):
        payload = b"\x00synthetic canonical TAR\xff"
        completed = subprocess.CompletedProcess([], 0, stdout=b"")
        with patch.object(guard.subprocess, "run", return_value=completed) as run:
            guard._docker(["build", "--network=none", "--pull=false", "--tag", "local/coolify-helper-fixture:test", "-"], payload)
        args, kwargs = run.call_args
        self.assertEqual(args[0][-1], "-")
        self.assertIs(kwargs["input"], payload)
        self.assertNotIn("stdin", kwargs)
        with patch.object(guard.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, stdout=b"")):
            with self.assertRaisesRegex(guard.VerificationError, "candidate_build_failed"):
                guard._docker(["image", "ls"])


if __name__ == "__main__":
    unittest.main()
