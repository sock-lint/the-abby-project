#!/usr/bin/env python3
"""Compare a checkout with an independently attested operator binding manifest.

This accepts a normalized operator manifest, not a raw Claude receipt schema.
The trusted owner/reviewer must supply its SHA256 independently. Git supplies
comparison facts only; this program never creates an approval or fetches refs.
Raw review payloads and private evidence references are neither read nor echoed.
The same process captures and verifies canonical TAR bytes from raw Git blobs.
An optional candidate build consumes those exact in-memory bytes on stdin;
the exported directory is diagnostic and is never the Docker build source.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile


CHECKOUT_ROOT = Path(__file__).resolve().parents[3]
HELPER_PATH = "scripts/operations/coolify_helper"
SOURCE_FIELDS = {"head", "root_tree", "helper_subtree", "expected_base"}
FINDINGS = {"H1", "H2", "M1", "M2", "M3", "M4", "M5",
            "RV366D-ACT-1", "RV366D-ACT-2", "SG-1", "RV366D-README-1", "N1", "N2", "N3", "N4", "N5"}
CHECKS = {"Frontend validation", "Backend validation", "API fixtures", "deployment-guards"}
BUILD_INPUTS = {"Dockerfile", "apply_patch.php", "helper_retry.php"}
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_CONTEXT_BYTES = 64 * 1024 * 1024


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
    _object(manifest, {"schema_version", "source", "build_inputs", "canonical_tar_sha256", "independent_review", "main_review", "hosted_ci", "all_source_gates_clear"}, "invalid_manifest_schema")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 3:
        raise VerificationError("unsupported_manifest_version")
    source = _source(manifest["source"], "invalid_source_binding")
    _object(manifest["build_inputs"], BUILD_INPUTS, "invalid_build_inputs")
    for digest in manifest["build_inputs"].values():
        _hex(digest, 64, "invalid_build_input_digest")
    _hex(manifest["canonical_tar_sha256"], 64, "invalid_canonical_tar_digest")
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


def _git(repo, *args, allow_failure=False, binary=False):
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_SYSTEM=os.devnull,
               GIT_CONFIG_GLOBAL=os.devnull, GIT_ATTR_NOSYSTEM="1",
               GIT_NO_REPLACE_OBJECTS="1", GIT_TERMINAL_PROMPT="0")
    try:
        result = subprocess.run(
            ["git", "--no-replace-objects", "--no-optional-locks",
             "-c", "core.fsmonitor=false", "-c", "core.attributesFile=" + os.devnull,
             "-c", "core.excludesFile=" + os.devnull, "-c", "core.filemode=true",
             "-c", "core.ignorecase=false", "-c", "status.submoduleSummary=false",
             "-c", "core.untrackedCache=false", "-C", str(repo), *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=not binary, timeout=30, env=env, check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
        raise VerificationError("git_comparison_unavailable") from error
    if result.returncode and not allow_failure:
        raise VerificationError("git_comparison_failed")
    return result


def _git_path(repo, name):
    path = Path(_git(repo, "rev-parse", "--git-path", name).stdout.strip())
    return path if path.is_absolute() else repo / path


def _safe_repository(repo):
    # Reject replacement inputs rather than silently giving the operator a
    # different interpretation of HEAD. All queries also disable replacement.
    if any(key in os.environ for key in ("GIT_REPLACE_REF_BASE", "GIT_NO_REPLACE_OBJECTS", "GIT_GRAFT_FILE")):
        raise VerificationError("git_replacement_environment")
    if _git(repo, "for-each-ref", "--format=%(refname)", "refs/replace").stdout:
        raise VerificationError("git_replacement_refs")
    for name in ("info/attributes", "info/grafts"):
        path = _git_path(repo, name)
        if path.is_symlink() or (path.exists() and path.stat().st_size):
            raise VerificationError("unsafe_git_info_file")
    keys = _git(repo, "config", "--local", "--null", "--name-only", "--list", "--includes").stdout.split("\0")
    unsafe = {"core.attributesfile", "core.fsmonitor", "core.worktree", "core.usereplacerefs",
              "core.sparsecheckout", "core.sparsecheckoutcone", "extensions.worktreeconfig"}
    if any(key.lower() in unsafe or key.lower().startswith(("filter.", "include.", "includeif.")) for key in keys):
        raise VerificationError("unsafe_git_local_config")
    if _git(repo, "rev-parse", "--show-object-format").stdout.strip() != "sha1":
        raise VerificationError("unsupported_git_object_format")
    # Index flags can hide tracked edits from ordinary status.
    if any(entry and (entry[0].islower() or entry[0] == "S") for entry in
           _git(repo, "ls-files", "-v", "-z").stdout.split("\0")):
        raise VerificationError("unsafe_git_index_flags")


def _blob_id(payload):
    return hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload, usedforsecurity=False).hexdigest()


def _context_parts(name):
    # A deliberately narrow, portable USTAR namespace. Reject every path before
    # creating the export, including otherwise legal Git names with newlines.
    if type(name) is not str or not 1 <= len(name) <= 99:
        raise VerificationError("unsafe_context_tree_entry")
    parts = name.split("/")
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) or part in (".", "..") or part.lower() == ".git" for part in parts):
        raise VerificationError("unsafe_context_tree_entry")
    return parts


def _inventory_tree_id(inventory):
    root = {}
    for name, (mode, payload) in inventory.items():
        parts = _context_parts(name)
        branch = root
        for part in parts[:-1]:
            branch = branch.setdefault(part, {})
            if type(branch) is not dict:
                raise VerificationError("invalid_tar_inventory")
        if parts[-1] in branch or mode not in ("100644", "100755") or type(payload) is not bytes:
            raise VerificationError("invalid_tar_inventory")
        branch[parts[-1]] = (mode, payload)

    def tree(branch):
        entries = []
        for name, value in branch.items():
            name = name.encode("ascii")
            if type(value) is dict:
                mode, oid, key = b"40000", tree(value), name + b"/"
            else:
                file_mode, payload = value
                mode, oid, key = file_mode.encode("ascii"), _blob_id(payload), name
            entries.append((key, mode + b" " + name + b"\0" + bytes.fromhex(oid)))
        payload = b"".join(entry for _, entry in sorted(entries))
        return hashlib.sha1(b"tree " + str(len(payload)).encode() + b"\0" + payload, usedforsecurity=False).hexdigest()

    return tree(root)


def _canonical_tar(inventory):
    _inventory_tree_id(inventory)
    directories = {"/".join(name.split("/")[:index]) for name in inventory
                   for index in range(1, len(name.split("/")))}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in sorted(set(inventory) | directories):
            member = tarfile.TarInfo(name)
            member.uid = member.gid = member.mtime = 0
            member.uname = member.gname = ""
            if name in directories:
                member.type, member.mode = tarfile.DIRTYPE, 0o755
                archive.addfile(member)
            else:
                mode, payload = inventory[name]
                member.type = tarfile.REGTYPE
                member.mode = 0o755 if mode == "100755" else 0o644
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
    return stream.getvalue()


def _capture_canonical_tar(directory):
    inventory = {}
    for parent, directories, files in os.walk(directory, followlinks=False):
        for name in directories + files:
            path = Path(parent) / name
            relative = path.relative_to(directory).as_posix()
            _context_parts(relative)
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                continue
            if not stat.S_ISREG(mode) or stat.S_IMODE(mode) not in (0o644, 0o755):
                raise VerificationError("export_context_unsafe_mode")
            inventory[relative] = ("100755" if mode & stat.S_IXUSR else "100644", path.read_bytes())
    return _canonical_tar(inventory)


def verify_canonical_tar(payload, expected_tree, expected_inputs):
    """Validate the actual captured archive without extracting any member."""
    inventory, directories, names = {}, set(), set()
    if type(payload) is not bytes or len(payload) > MAX_CONTEXT_BYTES + 4 * 1024 * 1024:
        raise VerificationError("invalid_canonical_tar")
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
            for member in archive:
                _context_parts(member.name)
                if member.name in names or len(names) >= 4096:
                    raise VerificationError("invalid_tar_inventory")
                names.add(member.name)
                if (member.uid != 0 or member.gid != 0 or member.mtime != 0 or member.uname or
                        member.gname or member.linkname or member.pax_headers):
                    raise VerificationError("noncanonical_tar_metadata")
                if member.type == tarfile.DIRTYPE and member.mode == 0o755 and member.size == 0:
                    directories.add(member.name)
                elif member.type == tarfile.REGTYPE and member.mode in (0o644, 0o755):
                    total += member.size
                    if total > MAX_CONTEXT_BYTES or member.size < 0:
                        raise VerificationError("invalid_tar_inventory")
                    stream = archive.extractfile(member)
                    data = stream.read() if stream is not None else b""
                    if len(data) != member.size:
                        raise VerificationError("invalid_tar_inventory")
                    inventory[member.name] = ("100755" if member.mode & stat.S_IXUSR else "100644", data)
                else:
                    raise VerificationError("unsafe_tar_member")
    except (tarfile.TarError, OSError) as error:
        raise VerificationError("invalid_canonical_tar") from error
    required_dirs = {"/".join(name.split("/")[:index]) for name in inventory
                     for index in range(1, len(name.split("/")))}
    if not inventory or directories != required_dirs or _inventory_tree_id(inventory) != expected_tree:
        raise VerificationError("tar_context_tree_mismatch")
    for name, expected in expected_inputs.items():
        if name not in inventory or hashlib.sha256(inventory[name][1]).hexdigest() != expected:
            raise VerificationError("tar_build_input_mismatch")
    if _canonical_tar(inventory) != payload:
        raise VerificationError("noncanonical_tar_bytes")


def _candidate_tag(tag):
    if type(tag) is not str or re.fullmatch(r"local/coolify-helper-[a-z0-9][a-z0-9_.-]{0,95}:[a-z0-9][a-z0-9_.-]{0,95}", tag) is None:
        raise VerificationError("invalid_candidate_tag")


def _docker(args, payload=None):
    try:
        result = subprocess.run(["docker", *args], input=payload, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=1800, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise VerificationError("candidate_build_unavailable") from error
    if result.returncode:
        raise VerificationError("candidate_build_failed")
    return result


def _build_candidate(tag, canonical_tar, verified_head):
    _candidate_tag(tag)
    _hex(verified_head, 40, "invalid_candidate_source_head")
    if _docker(["image", "ls", "--quiet", "--no-trunc", "--filter", "reference=" + tag]).stdout.strip():
        raise VerificationError("candidate_tag_already_exists")
    _docker(["build", "--network=none", "--pull=false", "--label",
             "lol.bos.coolify-helper-patch.source-commit=" + verified_head, "--tag", tag, "-"], canonical_tar)


def _tree_id(directory):
    """Hash exported filesystem bytes and modes, independently of Git output."""
    entries = []
    for path in directory.iterdir():
        mode = path.lstat().st_mode
        name = path.name.encode("utf-8")
        if stat.S_ISDIR(mode):
            tree_mode, oid, sort_key = b"40000", _tree_id(path), name + b"/"
        elif stat.S_ISREG(mode) and stat.S_IMODE(mode) in (0o644, 0o755):
            tree_mode = b"100755" if stat.S_IMODE(mode) == 0o755 else b"100644"
            oid, sort_key = _blob_id(path.read_bytes()), name
        else:
            raise VerificationError("export_context_unsafe_mode")
        entries.append((sort_key, tree_mode + b" " + name + b"\0" + bytes.fromhex(oid)))
    payload = b"".join(entry for _, entry in sorted(entries))
    return hashlib.sha1(b"tree " + str(len(payload)).encode() + b"\0" + payload, usedforsecurity=False).hexdigest()


def verify_exported_context(directory, expected_tree, expected_inputs):
    """Compare an owned export with the attested tree and raw build inputs."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir() or _tree_id(directory) != expected_tree:
        raise VerificationError("export_context_tree_mismatch")
    for name, expected in expected_inputs.items():
        path = directory / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise VerificationError("export_build_input_mismatch")


def _export_context(repo, source, expected_inputs, destination):
    destination = Path(destination).absolute()
    resolved = destination.resolve()
    if resolved == repo or repo in resolved.parents:
        raise VerificationError("export_context_inside_checkout")
    records = _git(repo, "ls-tree", "-rz", "--full-tree", source["helper_subtree"], binary=True).stdout.split(b"\0")
    entries = []
    for record in filter(None, records):
        try:
            metadata, path_bytes = record.split(b"\t", 1)
            mode, kind, oid = metadata.decode("ascii").split(" ")
            parts = _context_parts(path_bytes.decode("utf-8"))
        except (ValueError, UnicodeError) as error:
            raise VerificationError("invalid_context_tree_entry") from error
        if mode not in ("100644", "100755") or kind != "blob":
            raise VerificationError("unsafe_context_tree_entry")
        _hex(oid, 40, "invalid_context_blob_id")
        entries.append((parts, mode, oid))
    names = {"/".join(parts) for parts, _, _ in entries}
    if len(names) != len(entries) or any("/".join(parts[:index]) in names for parts, _, _ in entries for index in range(1, len(parts))):
        raise VerificationError("invalid_context_tree_entry")
    if not 1 <= len(entries) <= 4096:
        raise VerificationError("invalid_context_tree_size")
    try:
        destination.mkdir(mode=0o700)
    except OSError as error:
        raise VerificationError("export_context_not_fresh") from error
    try:
        total = 0
        for parts, mode, oid in entries:
            payload = _git(repo, "cat-file", "blob", oid, binary=True).stdout
            total += len(payload)
            if total > MAX_CONTEXT_BYTES or _blob_id(payload) != oid:
                raise VerificationError("invalid_raw_context_blob")
            path = destination.joinpath(*parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(payload)
            path.chmod(0o755 if mode == "100755" else 0o644)
        verify_exported_context(destination, source["helper_subtree"], expected_inputs)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return destination


def verify(manifest_path, expected_manifest_sha256, repo=CHECKOUT_ROOT, *, export_context, build_candidate_tag=None):
    """Verify, capture the reviewed context, and optionally build those bytes."""
    if build_candidate_tag is not None:
        _candidate_tag(build_candidate_tag)
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
    _safe_repository(repo)
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
    destination = _export_context(repo, actual, manifest["build_inputs"], export_context)
    try:
        _safe_repository(repo)
        if (_git(repo, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none").stdout or
                _git(repo, "rev-parse", "HEAD").stdout.strip() != actual["head"] or
                _git(repo, "rev-parse", "refs/remotes/origin/main").stdout.strip() != actual["expected_base"]):
            raise VerificationError("checkout_changed_during_export")
        verify_exported_context(destination, actual["helper_subtree"], manifest["build_inputs"])
        canonical_tar = _capture_canonical_tar(destination)
        verify_canonical_tar(canonical_tar, actual["helper_subtree"], manifest["build_inputs"])
        tar_digest = hashlib.sha256(canonical_tar).hexdigest()
        if tar_digest != manifest["canonical_tar_sha256"]:
            raise VerificationError("canonical_tar_digest_mismatch")
        if build_candidate_tag is not None:
            _build_candidate(build_candidate_tag, canonical_tar, actual["head"])
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {"schema_version": 3, "verified": True, "manifest_sha256": actual_digest, "source": actual,
            "exported_context_verified": True, "build_inputs": manifest["build_inputs"],
            "canonical_tar_sha256": tar_digest, "canonical_tar_verified": True,
            "candidate_build_completed": build_candidate_tag is not None,
            "expected_image_patch_receipt": {"patcher_sha256": manifest["build_inputs"]["apply_patch.php"],
                                             "retry_source_sha256": manifest["build_inputs"]["helper_retry.php"]},
            "image_patch_receipt_verified": False, "all_source_gates_clear": True}


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise VerificationError("invalid_arguments")


def main(argv=None):
    parser = _ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--export-context", required=True)
    parser.add_argument("--build-candidate-tag")
    try:
        args = parser.parse_args(argv)
        print(json.dumps(verify(args.manifest, args.expected_manifest_sha256, CHECKOUT_ROOT,
                                export_context=args.export_context, build_candidate_tag=args.build_candidate_tag), sort_keys=True))
        return 0
    except VerificationError as error:
        print(json.dumps({"schema_version": 3, "verified": False, "error": str(error)}, sort_keys=True))
        return 1
    except (OSError, UnicodeError, RecursionError, ValueError):
        print(json.dumps({"schema_version": 3, "verified": False, "error": "source_or_export_unavailable"}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
