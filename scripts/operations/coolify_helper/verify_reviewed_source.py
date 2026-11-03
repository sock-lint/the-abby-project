#!/usr/bin/env python3
"""Compare a checkout with an independently attested operator binding manifest.

This accepts a normalized operator manifest, not a raw Claude receipt schema.
The trusted owner/reviewer must supply its SHA256 independently. Git supplies
comparison facts only; this program never creates an approval or fetches refs.
Raw review payloads and private evidence references are neither read nor echoed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


CHECKOUT_ROOT = Path(__file__).resolve().parents[3]
HELPER_PATH = "scripts/operations/coolify_helper"
SOURCE_FIELDS = {"head", "root_tree", "helper_subtree", "expected_base"}
FINDINGS = {"H1", "H2", "M1", "M2", "M3", "M4", "M5"}
CHECKS = {"Frontend validation", "Backend validation", "API fixtures", "deployment-guards"}
MAX_MANIFEST_BYTES = 1024 * 1024


class VerificationError(ValueError):
    """A static error code suitable for a nonsecret operator receipt."""


def _object(value, required, code, optional=()):
    if type(value) is not dict or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise VerificationError(code)
    return value


def _text(value, code):
    if type(value) is not str or not value.strip() or len(value) > 4096:
        raise VerificationError(code)


def _hex(value, length, code):
    if type(value) is not str or re.fullmatch(rf"[a-f0-9]{{{length}}}", value) is None:
        raise VerificationError(code)


def _source(value, code):
    _object(value, SOURCE_FIELDS, code)
    for sha in value.values():
        _hex(sha, 40, code)
    return value


def _same_source(value, expected, code):
    if _source(value, code) != expected:
        raise VerificationError(code)


def _evidence(value, code):
    _object(value, {"ref", "sha256"}, code)
    _text(value["ref"], code)
    _hex(value["sha256"], 64, code)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError("duplicate_manifest_key")
        result[key] = value
    return result


def _validate_manifest(manifest):
    _object(manifest, {"schema_version", "source", "independent_review", "main_review", "hosted_ci", "all_source_gates_clear"}, "invalid_manifest_schema")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise VerificationError("unsupported_manifest_version")
    source = _source(manifest["source"], "invalid_source_binding")
    if manifest["all_source_gates_clear"] is not True:
        raise VerificationError("source_gates_not_clear")

    review = _object(manifest["independent_review"], {"author_family", "reviewer_family", "verdict", "source", "raw_receipt_sha256"}, "invalid_independent_review", {"owner_held_raw_receipt_path"})
    if review["author_family"] != "codex" or review["reviewer_family"] != "claude" or review["verdict"] != "clean":
        raise VerificationError("independent_review_not_clean")
    _same_source(review["source"], source, "independent_review_source_mismatch")
    _hex(review["raw_receipt_sha256"], 64, "invalid_raw_review_digest")
    if "owner_held_raw_receipt_path" in review:
        _text(review["owner_held_raw_receipt_path"], "invalid_raw_review_reference")

    main = _object(manifest["main_review"], {"verdict", "source", "findings"}, "invalid_main_review")
    if main["verdict"] != "clean":
        raise VerificationError("main_review_not_clean")
    _same_source(main["source"], source, "main_review_source_mismatch")
    _object(main["findings"], FINDINGS, "incomplete_main_findings")
    for finding in main["findings"].values():
        _object(finding, {"disposition", "evidence"}, "invalid_main_finding")
        if finding["disposition"] not in ("fixed", "not_applicable"):
            raise VerificationError("main_finding_unresolved")
        evidence = finding["evidence"]
        if type(evidence) is not list or not 1 <= len(evidence) <= 32:
            raise VerificationError("main_finding_evidence_missing")
        for item in evidence:
            _evidence(item, "invalid_main_finding_evidence")

    ci = _object(manifest["hosted_ci"], {"source", "checks"}, "invalid_hosted_ci")
    _same_source(ci["source"], source, "hosted_ci_source_mismatch")
    _object(ci["checks"], CHECKS, "incomplete_hosted_ci")
    for check in ci["checks"].values():
        _object(check, {"status", "conclusion", "head", "base", "evidence_ref", "evidence_sha256"}, "invalid_hosted_ci_check")
        if check["status"] != "completed" or check["conclusion"] != "success":
            raise VerificationError("hosted_ci_not_successful")
        if check["head"] != source["head"] or check["base"] != source["expected_base"]:
            raise VerificationError("hosted_ci_head_base_mismatch")
        _text(check["evidence_ref"], "invalid_hosted_ci_evidence")
        _hex(check["evidence_sha256"], 64, "invalid_hosted_ci_evidence")
    return source


def _git(repo, *args, allow_failure=False):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(repo), *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=30, env=env, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VerificationError("git_comparison_unavailable") from error
    if result.returncode and not allow_failure:
        raise VerificationError("git_comparison_failed")
    return result


def verify(manifest_path, expected_manifest_sha256, repo=CHECKOUT_ROOT):
    """Return only public Git identities and successful gate comparisons."""
    _hex(expected_manifest_sha256, 64, "invalid_expected_manifest_digest")
    try:
        with Path(manifest_path).open("rb") as stream:
            payload = stream.read(MAX_MANIFEST_BYTES + 1)
    except OSError as error:
        raise VerificationError("manifest_unavailable") from error
    if len(payload) > MAX_MANIFEST_BYTES:
        raise VerificationError("manifest_too_large")
    actual_digest = hashlib.sha256(payload).hexdigest()
    if actual_digest != expected_manifest_sha256:
        raise VerificationError("manifest_digest_mismatch")
    try:
        manifest = json.loads(payload.decode("utf-8"), object_pairs_hook=_unique_object)
    except VerificationError:
        raise
    except (UnicodeError, ValueError, RecursionError) as error:
        raise VerificationError("invalid_manifest_json") from error
    expected = _validate_manifest(manifest)
    repo = Path(repo).resolve()
    if _git(repo, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none").stdout:
        raise VerificationError("checkout_not_clean")
    actual = {
        "head": _git(repo, "rev-parse", "--verify", "HEAD").stdout.strip(),
        "root_tree": _git(repo, "rev-parse", "--verify", "HEAD^{tree}").stdout.strip(),
        "helper_subtree": _git(repo, "rev-parse", "--verify", f"HEAD:{HELPER_PATH}").stdout.strip(),
        "expected_base": _git(repo, "rev-parse", "--verify", "refs/remotes/origin/main").stdout.strip(),
    }
    for field in SOURCE_FIELDS:
        if actual[field] != expected[field]:
            raise VerificationError(f"git_{field}_mismatch")
    if _git(repo, "cat-file", "-t", actual["helper_subtree"]).stdout.strip() != "tree":
        raise VerificationError("helper_subtree_not_tree")
    if _git(repo, "merge-base", "--is-ancestor", actual["expected_base"], actual["head"], allow_failure=True).returncode:
        raise VerificationError("base_not_ancestor")
    return {"schema_version": 1, "verified": True, "manifest_sha256": actual_digest, "source": actual, "all_source_gates_clear": True}


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise VerificationError("invalid_arguments")


def main(argv=None):
    parser = _ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    try:
        args = parser.parse_args(argv)
        print(json.dumps(verify(args.manifest, args.expected_manifest_sha256, CHECKOUT_ROOT), sort_keys=True))
        return 0
    except VerificationError as error:
        print(json.dumps({"schema_version": 1, "verified": False, "error": str(error)}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
