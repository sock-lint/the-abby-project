"""Capture a chain-bound Engine contract using one owned never-started probe.

The expected plan digest is supplied independently by the trusted owner/reviewer.
Default observation never starts services or edits production configuration. An
explicit owner-authorized action can run the one exact bounded management up
command only after fresh chain/probe/contract checks. Runtime admission, drain,
startup/staging/recovery gates remain separate required operator evidence.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import sys
import stat

from compose_contract_projection import capture_chain, recheck_chain, safe_recipe, prove_and_reinsert, digest, controlled_docker_environment
from verify_activation_contract import APPLICATION_TEST, compare, contract, differences, check_port_collisions, verify_health

PREFIX = "com.docker.compose."
LABEL_KEYS = {"config-hash", "container-number", "depends_on", "image", "oneoff", "project",
              "project.config_files", "project.environment_file", "project.working_dir", "service", "version"}
OWNER_LABEL = "lol.bos.coolify-contract-probe.owner"


def local_run(argv, payload=None):
    result = subprocess.run(argv, input=payload, stdin=subprocess.DEVNULL if payload is None else None,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
                            env=controlled_docker_environment(),
                            timeout=180 if argv[:2] == ["docker", "compose"] and "up" in argv else 90)
    if result.returncode:
        raise ValueError("local probe observation failed")
    return result.stdout


def _one(raw):
    value = json.loads(raw)
    if not isinstance(value, list) or len(value) != 1:
        raise ValueError("expected exactly one Engine object")
    return value[0]


def trusted_state_directory(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("canonical private state path required")
    uid = os.geteuid()
    for directory in [path, *path.parents]:
        metadata = directory.lstat()
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid not in {0, uid}
                or metadata.st_mode & 0o022):
            raise ValueError("state directory has replaceable or untrusted ancestry")
        if (directory / ".git").exists():
            raise ValueError("private state must remain outside Git worktrees")
    if path.stat().st_uid != uid or path.stat().st_mode & 0o077:
        raise ValueError("effective-owner private state directory required")
    return path


def _service_hash(raw, service):
    match = re.fullmatch(re.escape(service) + r"\s+([0-9a-f]{64})", raw.decode().strip())
    if not match:
        raise ValueError("unsupported actual Compose hash format")
    return match.group(1)


def compose_argv(files, env_file, project, project_directory):
    argv = ["docker", "compose", "--project-name", project, "--project-directory", str(project_directory),
            "--env-file", str(env_file)]
    for path in files:
        argv += ["-f", str(path)]
    return argv


def normalize_labels(probe, *, token, probe_project, probe_file, probe_hash,
                     final_project, final_files, final_env, final_hash, project_directory, version, image):
    labels = probe["Config"]["Labels"]
    if labels.get(OWNER_LABEL) != token:
        raise ValueError("probe ownership mismatch")
    if {key[len(PREFIX):] for key in labels if key.startswith(PREFIX)} != LABEL_KEYS:
        raise ValueError("unsupported generated Compose label set")
    expected = {"config-hash": probe_hash, "container-number": "1", "image": image,
                "oneoff": "False", "project": probe_project, "project.config_files": str(probe_file),
                "project.environment_file": os.devnull, "project.working_dir": str(project_directory),
                "service": "coolify", "version": version}
    if any(labels.get(PREFIX + key) != value for key, value in expected.items()):
        raise ValueError("actual generated probe metadata differs")
    # depends_on is NOT ignored: it comes from the actual same-version probe
    # with the original resolved dependency declaration preserved. Stub services
    # are never created, started or contacted (--no-deps + exact project inventory).
    labels.pop(OWNER_LABEL)
    replacements = {"config-hash": final_hash, "project": final_project,
                    "project.config_files": ",".join(map(str, final_files)),
                    "project.environment_file": str(final_env), "project.working_dir": str(project_directory)}
    for key, value in replacements.items():
        labels[PREFIX + key] = value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def observe(plan_payload, *, expected_plan_sha256, operator_state_dir, reviewed_changes=None, expected_changes_sha256=None, runner=local_run):
    """Observe the actual chain and actual Engine itself; no supplied snapshots.

    Already staged files must match the externally attested plan. A source-only
    or probe-only approval cannot authorize the explicit management activation.
    """
    if not isinstance(plan_payload, bytes) or hashlib.sha256(plan_payload).hexdigest() != expected_plan_sha256:
        raise ValueError("external plan digest mismatch")
    plan = json.loads(plan_payload, object_pairs_hook=_unique_object)
    required = {"schema_version", "project", "service", "compose_files", "env_file", "expected_chain_ticket",
                "running_container_id", "candidate_image_id", "probe_token", "action", "tool_inputs"}
    optional = {"freeze_receipt_sha256"}
    if not required <= set(plan) or set(plan) - required - optional or type(plan["schema_version"]) is not int or plan["schema_version"] != 1 or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", plan["project"]) or plan["service"] != "coolify":
        raise ValueError("unsupported plan schema")
    if plan["action"] not in {"prepare_review", "probe_only", "activate_management"}:
        raise ValueError("unsupported owner action")
    if plan["action"] == "activate_management" and not re.fullmatch(r"[0-9a-f]{64}", plan.get("freeze_receipt_sha256", "")):
        raise ValueError("explicit owner freeze clearance required")
    tools = {"capture_activation_contract.py", "compose_contract_projection.py", "verify_activation_contract.py"}
    if set(plan["tool_inputs"]) != tools or any(hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest() != value for name, value in plan["tool_inputs"].items()):
        raise ValueError("actual operator tooling differs from reviewed plan")
    approved_changes = None
    if plan["action"] != "prepare_review":
        if not isinstance(reviewed_changes, bytes) or hashlib.sha256(reviewed_changes).hexdigest() != expected_changes_sha256:
            raise ValueError("reviewed difference digest mismatch")
        approved_changes = json.loads(reviewed_changes, object_pairs_hook=_unique_object)
    token = plan["probe_token"]
    if not re.fullmatch(r"[0-9a-f]{32}", token) or not re.fullmatch(r"[0-9a-f]{64}", plan["running_container_id"]):
        raise ValueError("invalid plan identity")
    candidate = plan["candidate_image_id"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", candidate):
        raise ValueError("immutable candidate required")
    files, env_file = list(map(Path, plan["compose_files"])), Path(plan["env_file"])
    if not files or any("," in str(path) or "\n" in str(path) for path in [*files, env_file]):
        raise ValueError("ambiguous file-chain identity")
    project_directory = files[0].parent
    ticket, rendered = capture_chain(files, env_file, plan["project"], "coolify", runner)
    if ticket != plan["expected_chain_ticket"]:
        raise ValueError("actual chain is not independently bound plan")
    declared = rendered["services"]["coolify"]
    if declared["image"] != candidate or declared.get("pull_policy") != "never":
        raise ValueError("actual chain image or explicit pull hold differs from plan")
    running = _one(runner(["docker", "inspect", plan["running_container_id"]]))
    if running.get("Id") != plan["running_container_id"] or not running.get("State", {}).get("Running"):
        raise ValueError("baseline running identity/state changed")
    if (running["Config"].get("Labels", {}).get(PREFIX + "project") != plan["project"]
            or running["Config"].get("Labels", {}).get(PREFIX + "service") != "coolify"
            or declared.get("container_name") != running.get("Name", "").lstrip("/")):
        raise ValueError("actual management project/service/name differs from bound plan")
    base_image = _one(runner(["docker", "image", "inspect", running["Image"]]))
    candidate_image = _one(runner(["docker", "image", "inspect", candidate]))
    if (candidate_image["Id"] != candidate or base_image["Id"] != running["Image"]
            or running["Config"].get("Volumes")):
        raise ValueError("candidate resolution or inherited runtime volume mismatch")
    safe = safe_recipe(declared, candidate_image["Config"].get("Volumes"), token)
    dependencies = copy.deepcopy(declared.get("depends_on", {}))
    if dependencies:
        safe["depends_on"] = dependencies
    safe_services = {"coolify": safe}
    for name in dependencies:
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name) or name == "coolify":
            raise ValueError("unsupported dependency reference")
        safe_services[name] = {"image": candidate, "network_mode": "none", "pull_policy": "never",
                               "healthcheck": {"test": ["CMD", "true"]}, "labels": {OWNER_LABEL: token}}
    state = trusted_state_directory(operator_state_dir)
    work = Path(tempfile.mkdtemp(prefix="owned-compose-probe-", dir=state))
    probe_file = work / "probe.json"
    probe_file.write_text(json.dumps({"services": safe_services}))
    probe_file.chmod(0o600)
    probe_project = "cfprobe" + token
    probe_command = compose_argv([probe_file], os.devnull, probe_project, project_directory)
    final_command = compose_argv(files, env_file, plan["project"], project_directory)
    probe_id = None
    if runner(["docker", "ps", "--all", "--quiet", "--no-trunc", "--filter", "label=" + PREFIX + "project=" + probe_project]).strip():
        raise ValueError("probe namespace already exists; preserve unknown resources")
    try:
        # Actual same-version default serialization/dollar roundtrip is captured;
        # it cannot be supplied as operator evidence instead of being observed.
        probe_render = json.loads(runner([*probe_command, "config", "--format", "json"]))
        if probe_render["services"]["coolify"].get("network_mode") != "none":
            raise ValueError("actual safe render gained network connectivity")
        raw_probe_hash = runner([*probe_command, "config", "--hash", "coolify"])
        probe_hash = _service_hash(raw_probe_hash, "coolify")
        raw_final_hash = runner([*final_command, "config", "--hash", "coolify"])
        version_raw = runner(["docker", "compose", "version", "--short"]).decode().strip()
        if (hashlib.sha256(raw_final_hash.decode().strip().encode()).hexdigest() != ticket["service_hash_output_sha256"]
                or hashlib.sha256(version_raw.encode()).hexdigest() != ticket["compose_version_sha256"]):
            raise ValueError("Compose metadata drift during probe")
        runner([*probe_command, "create", "--no-deps", "--no-build", "--pull", "never", "coolify"])
        ids = runner(["docker", "ps", "--all", "--quiet", "--no-trunc", "--filter", "label=" + PREFIX + "project=" + probe_project]).decode().split()
        if len(ids) != 1 or not re.fullmatch(r"[0-9a-f]{64}", ids[0]):
            raise ValueError("probe project did not create exactly one owned container")
        probe_id = ids[0]
        probe = _one(runner(["docker", "inspect", probe_id]))
        if probe.get("Id") != probe_id or probe.get("Image") != candidate or probe["Config"].get("Labels", {}).get(OWNER_LABEL) != token:
            raise ValueError("actual probe ownership/image mismatch")
        projected = prove_and_reinsert(running, probe, declared, declared, rendered["networks"],
                                       base_image["Config"], candidate_image["Config"])
        normalize_labels(projected, token=token, probe_project=probe_project, probe_file=probe_file,
                         probe_hash=probe_hash, final_project=plan["project"], final_files=files, final_env=env_file,
                         final_hash=_service_hash(raw_final_hash, "coolify"), project_directory=project_directory,
                         version=version_raw, image=candidate)
        # Health evidence comes from the actual rendered chain and actual Engine,
        # never a caller-supplied JSON health assertion.
        health = declared.get("healthcheck", {}).get("test")
        engine_health = probe["Config"].get("Healthcheck", {}).get("Test")
        verify_health(APPLICATION_TEST, health, engine_health, interpolated=True)
        proposal = {"schema_version": 1, "changes": [
            {"path": path, "before": old, "after": new}
            for path, old, new in differences(contract(running), contract(projected))]}
        if approved_changes is not None:
            compare(running, projected, approved_changes)
        inventory_ids = runner(["docker", "ps", "--quiet", "--no-trunc"]).decode().split()
        inventory = json.loads(runner(["docker", "inspect", *inventory_ids])) if inventory_ids else []
        check_port_collisions(projected, inventory, running["Id"])
        # Secret-bearing observations stay only in this fresh private host dir.
        for name, value in {"rendered.json": rendered, "running-inspect.json": running,
                            "probe-inspect.json": probe, "projected-inspect.json": projected}.items():
            path = work / name
            path.write_text(json.dumps(value))
            path.chmod(0o600)
        recheck_chain(ticket, files, env_file, plan["project"], "coolify", runner)
        receipt = {"schema_version": 1, "actual_chain_bound": True, "applied": False,
                   "plan_sha256": expected_plan_sha256, "reviewed_changes_sha256": expected_changes_sha256,
                   "chain_ticket_sha256": digest(ticket), "actual_probe_id": probe_id,
                   "safe_recipe_sha256": digest(probe_render), "projected_contract_sha256": digest(contract(projected)),
                   "application_health_test_verified": True, "reviewed_diff_verified": approved_changes is not None,
                   "owner_runtime_gates_verified_by_this_tool": False}
        if plan["action"] == "prepare_review":
            receipt.update(difference_proposal=proposal, activation_authorized=False)
        if plan["action"] == "activate_management":
            # Raw endpoint MAC is retained conservatively in the full contract.
            # Without a declared stable MAC the tool cannot predict the assigned
            # post-recreate value. A probe-only plan can still compare the rest.
            for key, endpoint in declared.get("networks", {}).items():
                name = rendered["networks"][key]["name"]
                if (endpoint or {}).get("mac_address") != running["NetworkSettings"]["Networks"][name].get("MacAddress"):
                    raise ValueError("activation needs independently reviewed stable endpoint identity")
            recheck_chain(ticket, files, env_file, plan["project"], "coolify", runner)
            runner([*final_command, "up", "-d", "--no-deps", "--no-build", "--pull", "never",
                    "--force-recreate", "--wait", "--wait-timeout", "120", "coolify"])
            installed_id = runner([*final_command, "ps", "--quiet", "coolify"]).decode().strip()
            if not re.fullmatch(r"[0-9a-f]{64}", installed_id):
                raise ValueError("installed management identity unavailable; no retry")
            installed = _one(runner(["docker", "inspect", installed_id]))
            compare(projected, installed, {"schema_version": 1, "changes": []})
            status = runner(["docker", "exec", installed_id, "curl", "--noproxy", "*", "--silent", "--show-error",
                             "--output", "/dev/null", "--write-out", "%{http_code}", "--max-time", "10",
                             "http://127.0.0.1:8080/api/health"]).decode().strip()
            if status != "200":
                raise ValueError("application health is not exact HTTP200; no retry")
            recheck_chain(ticket, files, env_file, plan["project"], "coolify", runner)
            receipt.update(applied=True, installed_container_id=installed_id, application_http_status=200)
        return receipt
    finally:
        if probe_id:
            last = _one(runner(["docker", "inspect", probe_id]))
            if (last.get("Id") != probe_id or last.get("Image") != candidate
                    or last["Config"].get("Labels", {}).get(OWNER_LABEL) != token
                    or last.get("State", {}).get("Status") != "created"
                    or last["State"].get("Running") or last["State"].get("Pid") != 0):
                raise ValueError("probe cleanup state/ownership changed; preserve for operator")
            runner(["docker", "rm", probe_id])
        # Root-private recipe/snapshot evidence stays in this owned state dir.
        # Cleanup of that evidence follows the separately reviewed recovery
        # retention plan. Never remove a shared state directory or private data.


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError("invalid arguments")


def main(argv=None):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--operator-state-dir", required=True)
    parser.add_argument("--reviewed-changes")
    parser.add_argument("--expected-changes-sha256")
    try:
        args = parser.parse_args(argv)
        result = observe(Path(args.plan).read_bytes(), expected_plan_sha256=args.expected_plan_sha256,
                         operator_state_dir=args.operator_state_dir,
                         reviewed_changes=Path(args.reviewed_changes).read_bytes() if args.reviewed_changes else None,
                         expected_changes_sha256=args.expected_changes_sha256)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
        print(json.dumps({"schema_version": 1, "actual_chain_bound": False, "error": "chain_probe_or_apply_failed",
                          "automatic_retry": False, "keep_operator_admission_holds": True}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
