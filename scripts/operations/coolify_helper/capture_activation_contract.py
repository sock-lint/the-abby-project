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

from compose_contract_projection import capture_chain, recheck_chain, safe_recipe, prove_and_reinsert, digest, controlled_docker_environment, observe_runtime, selected_image_identity, model_expected_running_defaults
from verify_activation_contract import APPLICATION_TEST, compare, contract, differences, check_port_collisions, verify_health

PREFIX = "com.docker.compose."
LABEL_KEYS = {"config-hash", "container-number", "depends_on", "image", "oneoff", "project",
              "project.config_files", "project.environment_file", "project.working_dir", "service", "version"}
OWNER_LABEL = "lol.bos.coolify-contract-probe.owner"
PROBE_FLAGS = ("--no-start", "--no-deps", "--no-build", "--pull", "--no-recreate", "--force-recreate", "--wait", "--wait-timeout")
SUPPORTED_COMPOSE_VERSION = "5.7.0"
MAX_FREEZE_RECEIPT_BYTES = 1024 * 1024


class OperationFailure(ValueError):
    def __init__(self, status):
        super().__init__("chain/probe/management operation failed; inspect private status")
        self.status = status


class OperationState:
    """Durable nonsecret markers distinguish mutation from validation failure."""
    def __init__(self, work):
        self.work = work
        self.result = None
        self.status = {"stage": "pre-mutation", "up_scope": "management-recreation", "up_executed": False,
                       "up_succeeded": False, "installed_container_id": None, "post_up_inspect_sha256": None,
                       "actual_chain_bound": False,
                       "application_http_status": None, "owned_probe_cleanup_verified": False,
                       "freeze_receipt_bytes_verified": False, "verified_freeze_receipt_sha256": None,
                       "freeze_receipt_recheck_verified": False,
                       "owner_runtime_gates_verified_by_this_tool": False,
                       "private_operation_state_id": work.name, "automatic_retry": False,
                       "automatic_rollback": False, "keep_operator_admission_holds": True}
        self.persist()

    def persist(self):
        temporary = self.work / "operation-status.tmp"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(self.status, sort_keys=True).encode())
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.work / "operation-status.json")
        descriptor = os.open(self.work, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def update(self, **values):
        self.status.update(values)
        self.persist()

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        if error is not None:
            if self.status["stage"] == "success":
                self.status["stage"] = "post-up-cleanup-failed"
            self.status.update(failed=True, error_class=type(error).__name__)
        try:
            self.persist()
        except OSError as persistence_error:
            prior_stage = self.status["stage"]
            if error is not None:
                self.status["prior_error_class"] = type(error).__name__
            self.status.update(stage="status-persistence-failed", prior_stage=prior_stage,
                               failed=True, error_class=type(persistence_error).__name__,
                               status_persistence_failed=True, last_durable_state_current=False)
            error = persistence_error
        if error is not None:
            raise OperationFailure(dict(self.status)) from error
        if self.result is not None:
            self.result.update(self.status)
        return False


def private_bytes(work, name, payload):
    if type(payload) is not bytes:
        raise ValueError("private evidence bytes required")
    path = work / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(payload).hexdigest()


def private_json(work, name, value):
    return private_bytes(work, name, json.dumps(value).encode())


def application_status(runner, container_id):
    raw = runner(["docker", "exec", container_id, "curl", "--noproxy", "*", "--silent", "--show-error",
                  "--output", "/dev/null", "--write-out", "%{http_code}", "--max-time", "10",
                  "http://127.0.0.1:8080/api/health"]).decode().strip()
    return int(raw) if re.fullmatch(r"[0-9]{3}", raw) else None


def capture_post_up(runner, final_command, operation):
    installed_id = runner([*final_command, "ps", "--quiet", "coolify"]).decode().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", installed_id):
        raise ValueError("installed management identity unavailable; no retry")
    operation.update(installed_container_id=installed_id)
    installed = _one(runner(["docker", "inspect", installed_id]))
    if installed.get("Id") != installed_id:
        raise ValueError("installed inspect identity differs")
    digest_value = private_json(operation.work, "post-up-inspect.json", installed)
    operation.update(post_up_inspect_sha256=digest_value)
    return installed


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


def _freeze_metadata(value):
    # Reading can change atime; it is deliberately not identity evidence.
    return (value.st_dev, value.st_ino, value.st_size, value.st_uid, value.st_mode,
            value.st_mtime_ns, value.st_ctime_ns)


def capture_freeze_receipt(path, state, expected_sha256):
    """Capture opaque reviewed bytes, without inferring runtime approval.

    The independent plan digest is authority for both exact path and raw SHA.
    No receipt schema, issuer, freshness or operational semantics are inferred.
    """
    state = trusted_state_directory(state)
    if type(path) is not str or type(expected_sha256) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("independently bound freeze receipt path and digest required")
    filename = Path(path)
    if (not filename.is_absolute() or str(filename) != path or filename.resolve() != filename
            or filename.parent != state):
        raise ValueError("freeze receipt must be a canonical private-state child")
    try:
        descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) & 0o077
                    or not 0 < before.st_size <= MAX_FREEZE_RECEIPT_BYTES):
                raise ValueError("bounded owner-private regular freeze receipt required")
            payload = stream.read(MAX_FREEZE_RECEIPT_BYTES + 1)
            after = os.fstat(stream.fileno())
    except OSError:
        raise ValueError("freeze receipt capture unavailable") from None
    if (not payload or len(payload) != before.st_size or _freeze_metadata(before) != _freeze_metadata(after)
            or hashlib.sha256(payload).hexdigest() != expected_sha256):
        raise ValueError("freeze receipt bytes or identity differ from approved digest")
    return {"path": path, "payload": payload, "metadata": _freeze_metadata(after), "sha256": expected_sha256}


def recheck_freeze_receipt(captured, state):
    current = capture_freeze_receipt(captured["path"], state, captured["sha256"])
    if current["metadata"] != captured["metadata"] or current["payload"] != captured["payload"]:
        raise ValueError("freeze receipt identity or bytes changed before mutation")


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


def check_probe_capabilities(runner):
    help_text = runner(["docker", "compose", "up", "--help"]).decode()
    if any(not re.search(r"(?:^|\s)" + re.escape(flag) + r"(?:\s|=|,|$)", help_text) for flag in PROBE_FLAGS):
        raise ValueError("actual Compose no-start options unsupported")
    return hashlib.sha256(help_text.encode()).hexdigest()


def owned_disposables(runner, project, token, image, services, image_environment):
    ids = runner(["docker", "ps", "--all", "--quiet", "--no-trunc", "--filter", "label=" + PREFIX + "project=" + project]).decode().split()
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[0-9a-f]{64}", item) for item in ids):
        raise ValueError("invalid disposable project inventory")
    result = {}
    for container_id in ids:
        row = _one(runner(["docker", "inspect", container_id]))
        config, state, host = row["Config"], row["State"], row["HostConfig"]
        labels = config.get("Labels") or {}
        service = labels.get(PREFIX + "service")
        if (row.get("Id") != container_id or row.get("Image") != image or service not in services
                or service in result or labels.get(OWNER_LABEL) != token or labels.get(PREFIX + "project") != project
                or row.get("Name", "").lstrip("/") != services[service]["container_name"]
                or state.get("Status") != "created" or state.get("Running") is not False
                or type(state.get("Pid")) is not int or state["Pid"] != 0
                or not re.fullmatch(r"0001-01-01T00:00:00(?:\.0+)?Z", state.get("StartedAt", ""))
                or host.get("NetworkMode") != "none" or any(host.get(field) for field in ("PortBindings", "Binds", "Mounts", "VolumesFrom"))
                or row.get("Mounts") or config.get("Volumes")
                or set(row["NetworkSettings"].get("Networks", {})) - {"none"}):
            raise ValueError("disposable ownership or never-started isolation mismatch")
        if service != "coolify" and (sorted(config.get("Env") or []) != sorted(image_environment or [])
                                      or config.get("Entrypoint") != ["/bin/false"] or config.get("Cmd") != []):
            raise ValueError("dependency stub gained private environment or application entrypoint")
        result[service] = row
    return result


def normalize_labels(probe, *, token, probe_project, probe_file, probe_hash,
                     final_project, final_files, final_env, final_hash, project_directory, version, image,
                     replacement_name):
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
    # with the original resolved dependency declaration preserved and the same
    # up --no-deps semantics as the real operation. Stubs remain declared but
    # the observed successful created set must contain only management.
    labels.pop(OWNER_LABEL)
    replacements = {"config-hash": final_hash, "project": final_project,
                    "project.config_files": ",".join(map(str, final_files)),
                    "project.environment_file": str(final_env), "project.working_dir": str(project_directory)}
    for key, value in replacements.items():
        labels[PREFIX + key] = value
    # Independently reproduced for exactly 5.7.0 with an explicit container_name:
    # force-recreate stamps the OLD NAME without slash, not the old container ID.
    # Keep it in the proposal and full installed comparison; never ignore it.
    labels[PREFIX + "replace"] = replacement_name


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
    optional = {"freeze_receipt_path", "freeze_receipt_sha256"}
    if not required <= set(plan) or set(plan) - required - optional or type(plan["schema_version"]) is not int or plan["schema_version"] != 1 or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", plan["project"]) or plan["service"] != "coolify":
        raise ValueError("unsupported plan schema")
    if plan["action"] not in {"prepare_review", "probe_only", "activate_management"}:
        raise ValueError("unsupported owner action")
    if (plan["action"] == "activate_management" and not optional <= set(plan)
            or plan["action"] != "activate_management" and set(plan) & optional):
        raise ValueError("activation requires exact freeze receipt path and digest")
    state = trusted_state_directory(operator_state_dir)
    freeze = (capture_freeze_receipt(plan["freeze_receipt_path"], state, plan["freeze_receipt_sha256"])
              if plan["action"] == "activate_management" else None)
    tools = {"capture_activation_contract.py", "compose_contract_projection.py", "verify_activation_contract.py"}
    captured_hashes = globals().get("_TRUSTED_TOOL_SHA256")
    if captured_hashes != plan["tool_inputs"]:
        raise ValueError("operator tools require verified captured-buffer loading")
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
    runtime_proof = observe_runtime(runner)
    if runtime_proof["version_sha256"] != ticket["docker_runtime_version_sha256"]:
        raise ValueError("Docker runtime identity changed during capture")
    _, expected_image_label, image_identity_evidence = selected_image_identity(candidate_image, declared.get("platform"), runner)
    safe = safe_recipe(declared, candidate_image["Config"].get("Volumes"), token)
    dependencies = copy.deepcopy(declared.get("depends_on", {}))
    if dependencies:
        safe["depends_on"] = dependencies
    safe_services = {"coolify": safe}
    for name in dependencies:
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", name) or name == "coolify":
            raise ValueError("unsupported dependency reference")
        safe_services[name] = {"image": candidate, "network_mode": "none", "pull_policy": "never",
                              "container_name": "coolify-contract-dependency-" + token + "-" + name,
                              "entrypoint": ["/bin/false"], "command": [],
                              "healthcheck": {"test": ["CMD", "true"]}, "labels": {OWNER_LABEL: token}}
    probe_help_sha256 = check_probe_capabilities(runner)
    work = Path(tempfile.mkdtemp(prefix="owned-compose-probe-", dir=state))
    if freeze is not None:
        if private_bytes(work, "verified-freeze-receipt.bin", freeze["payload"]) != freeze["sha256"]:
            raise ValueError("private freeze evidence digest mismatch")
        private_json(work, "freeze-receipt-identity.json", {key: value for key, value in freeze.items() if key != "payload"})
    probe_file = work / "probe.json"
    probe_file.write_text(json.dumps({"services": safe_services}))
    probe_file.chmod(0o600)
    probe_project = "cfprobe" + token
    probe_command = compose_argv([probe_file], os.devnull, probe_project, project_directory)
    final_command = compose_argv(files, env_file, plan["project"], project_directory)
    probe_id = None
    if runner(["docker", "ps", "--all", "--quiet", "--no-trunc", "--filter", "label=" + PREFIX + "project=" + probe_project]).strip():
        raise ValueError("probe namespace already exists; preserve unknown resources")
    private_json(work, "rendered.json", rendered)
    private_json(work, "running-inspect.json", running)
    operation = OperationState(work)
    if freeze is not None:
        operation.update(freeze_receipt_bytes_verified=True, verified_freeze_receipt_sha256=freeze["sha256"])
    with operation:
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
            if version_raw != SUPPORTED_COMPOSE_VERSION:
                raise ValueError("force-recreate metadata behavior requires separately reviewed Compose version")
            if (hashlib.sha256(raw_final_hash.decode().strip().encode()).hexdigest() != ticket["service_hash_output_sha256"]
                    or hashlib.sha256(version_raw.encode()).hexdigest() != ticket["compose_version_sha256"]):
                raise ValueError("Compose metadata drift during probe")
            runner([*probe_command, "up", "--no-start", "--no-deps", "--no-build", "--pull", "never", "--no-recreate", "coolify"])
            rows = owned_disposables(runner, probe_project, token, candidate, safe_services, candidate_image["Config"].get("Env"))
            if set(rows) != {"coolify"}:
                raise ValueError("actual created service set differs from exact disposable recipe")
            probe = rows["coolify"]
            probe_id = probe["Id"]
            private_json(work, "probe-inspect.json", probe)
            projected = prove_and_reinsert(running, probe, declared, declared, rendered["networks"],
                                           base_image["Config"], candidate_image["Config"])
            projected = model_expected_running_defaults(projected, declared, runtime_proof)
            normalize_labels(projected, token=token, probe_project=probe_project, probe_file=probe_file,
                             probe_hash=probe_hash, final_project=plan["project"], final_files=files, final_env=env_file,
                             final_hash=_service_hash(raw_final_hash, "coolify"), project_directory=project_directory,
                             version=version_raw, image=expected_image_label, replacement_name=running["Name"].lstrip("/"))
            # Health evidence comes from the actual rendered chain and actual Engine,
            # never a caller-supplied JSON health assertion.
            health = declared.get("healthcheck", {}).get("test")
            engine_health = probe["Config"].get("Healthcheck", {}).get("Test")
            verify_health(APPLICATION_TEST, health, engine_health, interpolated=True)
            proposal = {"schema_version": 1, "changes": [
                {"path": path, "before": old, "after": new}
                for path, old, new in differences(contract(running), contract(projected))]}
            private_json(work, "projected-inspect.json", projected)
            if approved_changes is not None:
                compare(running, projected, approved_changes)
            inventory_ids = runner(["docker", "ps", "--quiet", "--no-trunc"]).decode().split()
            inventory = json.loads(runner(["docker", "inspect", *inventory_ids])) if inventory_ids else []
            check_port_collisions(projected, inventory, running["Id"])
            recheck_chain(ticket, files, env_file, plan["project"], "coolify", runner)
            operation.update(actual_chain_bound=True)
            receipt = {"schema_version": 1, "actual_chain_bound": True, "applied": False,
                       "plan_sha256": expected_plan_sha256, "reviewed_changes_sha256": expected_changes_sha256,
                       "chain_ticket_sha256": digest(ticket), "actual_probe_id": probe_id,
                       "safe_recipe_sha256": digest(probe_render), "projected_contract_sha256": digest(contract(projected)),
                       "compose_no_start_help_sha256": probe_help_sha256,
                       "owned_created_service_count": len(rows),
                       "image_identity_evidence": image_identity_evidence,
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
                recheck_freeze_receipt(freeze, state)
                operation.update(stage="up-running", up_executed=True, freeze_receipt_recheck_verified=True)
                try:
                    runner([*final_command, "up", "-d", "--no-deps", "--no-build", "--pull", "never",
                            "--force-recreate", "--wait", "--wait-timeout", "120", "coolify"])
                except Exception:
                    operation.update(stage="up-failed")
                    try:
                        capture_post_up(runner, final_command, operation)
                    except Exception:
                        operation.update(installed_identity_unresolved=True)
                    raise
                operation.update(stage="post-up-inspect", up_succeeded=True)
                installed = capture_post_up(runner, final_command, operation)
                installed_id = installed["Id"]
                try:
                    compare(projected, installed, {"schema_version": 1, "changes": []})
                except ValueError:
                    operation.update(stage="post-up-contract-mismatch")
                    try:
                        operation.update(application_http_status=application_status(runner, installed_id))
                    except Exception:
                        operation.update(application_http_status_unresolved=True)
                    raise
                operation.update(stage="http-check-running")
                try:
                    status = application_status(runner, installed_id)
                    operation.update(application_http_status=status)
                    if status != 200:
                        raise ValueError("application health is not exact HTTP200; no retry")
                except Exception:
                    operation.update(stage="http-failed")
                    raise
                operation.update(stage="post-up-chain-check")
                try:
                    recheck_chain(ticket, files, env_file, plan["project"], "coolify", runner)
                except Exception:
                    operation.update(stage="post-up-chain-mismatch")
                    raise
                operation.update(stage="success")
                receipt.update(applied=True)
            operation.result = receipt
            return receipt
        finally:
            # Also covers partial creation before the management probe ID existed.
            # Validate the ENTIRE discovered subset before removing any resource.
            cleanup = owned_disposables(runner, probe_project, token, candidate, safe_services, candidate_image["Config"].get("Env"))
            for service, row in cleanup.items():
                runner(["docker", "rm", row["Id"]])
            operation.update(owned_probe_cleanup_verified=True)
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
    except OperationFailure as error:
        print(json.dumps({"schema_version": 1, "error": "chain_probe_or_apply_failed", **error.status}), file=sys.stderr)
        return 1
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
        print(json.dumps({"schema_version": 1, "actual_chain_bound": False, "error": "chain_probe_or_apply_failed",
                          "stage": "pre-mutation", "up_executed": False, "up_succeeded": False,
                          "installed_container_id": None, "post_up_inspect_sha256": None,
                          "automatic_retry": False, "automatic_rollback": False,
                          "keep_operator_admission_holds": True}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
