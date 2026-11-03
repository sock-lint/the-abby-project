"""Actual-command dataflow tests with synthetic Compose/Engine observations."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import capture_activation_contract as driver
from compose_contract_projection import capture_chain, digest, TESTED_CLIENT, TESTED_SERVER, OCI_INDEX, OCI_MANIFEST
from verify_activation_contract import APPLICATION_TEST


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class SyntheticEngine:
    """No Docker calls: observe arguments/files as a local fake Engine would."""
    def __init__(self, directory):
        self.directory = directory
        self.base, self.candidate = "sha256:" + "1" * 64, "sha256:" + "2" * 64
        self.running_id, self.probe_id = "a" * 64, "b" * 64
        self.calls, self.created, self.removed, self.up = [], False, False, False
        self.mutate_after_create = False
        self.unexpected_label = False
        self.probe_started = False
        self.health_override = None
        self.rows = {}
        self.removed_ids = []
        self.partial_create_failure = False
        self.unsafe_stub = False
        self.create_help = b"--no-start --no-deps --no-build --pull policy --no-recreate --force-recreate --wait --wait-timeout\n"
        self.version = b"5.6.1\n"
        self.fail_up = True
        self.wrong_replace = False
        self.http_status = b"200"
        self.installed = None
        self.runtime = {"Client": {**TESTED_CLIENT, "Context": "default", "Experimental": None}, "Server": dict(TESTED_SERVER)}
        self.selected_id = "sha256:" + "3" * 64
        self.bad_selected_platform = False
        self.wrong_image_label = False
        self.env = directory / ".env"
        self.env.write_text("SYNTHETIC=PRIVATE-SYNTHETIC-SECRET\n")
        self.compose = directory / "compose.json"
        self.service = {"image": self.candidate, "pull_policy": "never", "container_name": "coolify", "command": None, "entrypoint": None,
                        "working_dir": "/var/www/html", "environment": {"SYNTHETIC": "PRIVATE-SYNTHETIC-SECRET"},
                        "healthcheck": {"test": APPLICATION_TEST}, "depends_on": {"redis": {"condition": "service_healthy"}},
                        "ports": [{"mode": "ingress", "target": 8080, "published": "18080", "host_ip": "127.0.0.1", "protocol": "tcp"}],
                        "volumes": [{"type": "bind", "source": "/synthetic/data", "target": "/data", "read_only": True}],
                        "networks": {"coolify": {"aliases": ["coolify-realtime"], "mac_address": "02:00:00:00:00:10"}}}
        self.rendered = {"services": {"coolify": self.service}, "networks": {"coolify": {"name": "coolify", "external": True}}}
        self.compose.write_text(json.dumps(self.rendered))
        self.image_config = {"ExposedPorts": {"8080/tcp": {}}, "Volumes": None}
        self.running = {"Id": self.running_id, "Image": self.base, "Name": "/coolify", "Path": "/init", "Args": [],
                        "Config": {"Hostname": self.running_id[:12], "Env": ["SYNTHETIC=PRIVATE-SYNTHETIC-SECRET"],
                                   "Image": self.base, "ExposedPorts": {"8080/tcp": {}}, "Volumes": None,
                                   "WorkingDir": "/var/www/html", "Entrypoint": ["/init"], "Cmd": [], "User": "www-data",
                                   "Healthcheck": {"Test": ["CMD", "/healthcheck"]}, "Labels": {"com.docker.compose.version": "2.38.2", "com.docker.compose.project": "source", "com.docker.compose.service": "coolify"}},
                        "HostConfig": {"NetworkMode": "coolify", "Binds": ["/synthetic/data:/data:ro"], "OomKillDisable": None,
                                       "PortBindings": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18080"}]},
                                       **{f"FutureField{n}": None for n in range(59)}},
                        "Mounts": [{"Type": "bind", "Source": "/synthetic/data", "Destination": "/data", "RW": False, "Propagation": "rprivate"}],
                        "State": {"Running": True}, "NetworkSettings": {"Ports": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18080"}]},
                            "Networks": {"coolify": {"Aliases": ["coolify", "coolify", "coolify-realtime"], "MacAddress": "02:00:00:00:00:10",
                                                      "IPAddress": "192.0.2.10", "GlobalIPv6Address": "2001:db8::10", "IPAMConfig": None,
                                                      "DriverOpts": None}}}}

    def run(self, argv, payload=None):
        self.calls.append(argv)
        if argv == ["docker", "version", "--format", "{{json .}}"]:
            return json.dumps(self.runtime).encode()
        if argv[:3] == ["docker", "compose", "version"]:
            return self.version
        if argv == ["docker", "compose", "up", "--help"]:
            return self.create_help
        if argv[:2] == ["docker", "compose"]:
            path = Path(argv[argv.index("-f") + 1])
            rendered = json.loads(path.read_bytes())
            if "config" in argv:
                if "--hash" in argv:
                    return ("coolify " + digest(rendered["services"]["coolify"]) + "\n").encode()
                return json.dumps(rendered).encode()
            if "up" in argv and "--no-start" in argv:
                allowed = {"--no-start", "--no-deps", "--no-build", "--pull", "--no-recreate"}
                if any(item.startswith("--") and item not in allowed for item in argv[argv.index("up") + 1:]):
                    raise ValueError("unsupported actual Compose no-start option")
                self.created = True
                safe = rendered["services"]["coolify"]
                if safe["network_mode"] != "none" or safe["ports"] or safe["volumes"]:
                    raise AssertionError("unsafe probe recipe")
                self.probe = copy.deepcopy(self.running)
                self.probe.update(Id=self.probe_id, Image=self.candidate, Name="/" + safe["container_name"],
                                  Mounts=[], State={"Status": "running" if self.probe_started else "created", "Running": self.probe_started, "Pid": 1 if self.probe_started else 0, "StartedAt": "0001-01-01T00:00:00Z"})
                self.probe["Config"].update(Hostname=self.probe_id[:12], Image=self.candidate,
                    Env=[key + "=" + value for key, value in safe["environment"].items()],
                    Healthcheck={"Test": self.health_override or safe["healthcheck"]["test"]})
                self.probe["HostConfig"].update(NetworkMode="none", Binds=[], PortBindings={}, OomKillDisable=False)
                self.probe["NetworkSettings"] = {"Ports": {}, "Networks": {"none": {}}}
                project = argv[argv.index("--project-name") + 1]
                generated = {"config-hash": digest(safe), "container-number": "1", "depends_on": "",
                    "image": self.candidate if self.wrong_image_label else self.selected_id, "oneoff": "False", "project": project, "project.config_files": str(path),
                    "project.environment_file": "/dev/null", "project.working_dir": str(self.directory), "service": "coolify", "version": "5.6.1"}
                labels = {driver.PREFIX + key: value for key, value in generated.items()}
                labels.update(safe["labels"])
                if self.unexpected_label:
                    labels[driver.PREFIX + "unreviewed-future"] = "unexpected"
                self.probe["Config"]["Labels"] = labels
                self.rows = {self.probe_id: self.probe}
                for index, (name, stub) in enumerate(rendered["services"].items()):
                    if name == "coolify" or not self.unsafe_stub:
                        continue
                    row = copy.deepcopy(self.probe)
                    row["Id"] = format(index + 12, "x") * 64
                    row["Name"] = "/" + stub["container_name"]
                    row["Config"].update(Env=[], Entrypoint=["/bin/false"], Cmd=[])
                    row["Config"]["Labels"][driver.PREFIX + "service"] = name
                    if self.unsafe_stub:
                        row["Config"]["Labels"][driver.OWNER_LABEL] = "unknown-owner"
                    self.rows[row["Id"]] = row
                if self.partial_create_failure:
                    raise ValueError("synthetic partial dependency creation failure")
                if self.mutate_after_create:
                    self.env.write_text("SYNTHETIC=drift-after-create\n")
                return b""
            if "up" in argv:
                self.up = True
                if self.fail_up:
                    raise ValueError("synthetic failed recreation; must never retry")
                snapshot = max((self.directory / "state").glob("*/projected-inspect.json"), key=lambda item: item.stat().st_mtime_ns)
                self.installed = json.loads(snapshot.read_bytes())
                self.installed.update(Id="e" * 64, Name="/coolify", State={"Running": True})
                self.installed["Config"]["Hostname"] = "e" * 12
                if self.wrong_replace:
                    self.installed["Config"]["Labels"][driver.PREFIX + "replace"] = "wrong-old-name"
                return b""
            if "ps" in argv:
                return self.installed["Id"].encode()
        if argv[:3] == ["docker", "image", "inspect"]:
            if "--help" in argv:
                return b"--platform string\n"
            image_id = self.selected_id if "--platform" in argv else argv[3]
            value = {"Id": image_id, "Config": self.image_config, "RootFS": {"Type": "layers", "Layers": ["sha256:" + "4" * 64]},
                     "Os": "linux", "Architecture": "amd64", "Variant": "",
                     "Descriptor": {"mediaType": OCI_MANIFEST if "--platform" in argv else OCI_INDEX, "digest": image_id}}
            if "--platform" in argv and self.bad_selected_platform:
                value["Architecture"] = "arm64"
            return json.dumps([value]).encode()
        if argv[:2] == ["docker", "inspect"]:
            rows = [self.running if item == self.running_id else self.installed if self.installed and item == self.installed["Id"] else self.rows[item] for item in argv[2:]]
            return json.dumps(rows).encode()
        if argv[:2] == ["docker", "ps"]:
            return ("\n".join(self.rows) if "--all" in argv else self.running_id).encode()
        if argv[:2] == ["docker", "rm"]:
            self.removed_ids.append(argv[2])
            self.rows.pop(argv[2])
            self.removed = not self.rows
            return b""
        if argv[:2] == ["docker", "exec"]:
            return self.http_status
        raise AssertionError("unexpected actual command")


class CaptureDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path.home())
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.engine = SyntheticEngine(self.directory)
        self.state = self.directory / "state"
        self.state.mkdir(mode=0o700)
        ticket, _ = capture_chain([self.engine.compose], self.engine.env, "source", "coolify", self.engine.run)
        self.plan = {"schema_version": 1, "project": "source", "service": "coolify", "compose_files": [str(self.engine.compose)],
                     "env_file": str(self.engine.env), "expected_chain_ticket": ticket, "running_container_id": self.engine.running_id,
                     "candidate_image_id": self.engine.candidate, "probe_token": "3" * 32, "action": "prepare_review",
                     "tool_inputs": {name: sha((Path(driver.__file__).parent / name).read_bytes()) for name in
                                     ("capture_activation_contract.py", "compose_contract_projection.py", "verify_activation_contract.py")}}
        loaded = patch.object(driver, "_TRUSTED_TOOL_SHA256", self.plan["tool_inputs"], create=True)
        loaded.start()
        self.addCleanup(loaded.stop)

    def observe(self, changes=None):
        raw = json.dumps(self.plan).encode()
        return driver.observe(raw, expected_plan_sha256=sha(raw), operator_state_dir=self.state,
                              reviewed_changes=changes, expected_changes_sha256=sha(changes) if changes else None, runner=self.engine.run)

    def test_prepare_owns_actual_disconnected_probe_and_only_exports_fingerprints(self):
        result = self.observe()
        self.assertTrue(result["actual_chain_bound"])
        self.assertFalse(result["reviewed_diff_verified"])
        self.assertFalse(result["activation_authorized"])
        self.assertNotIn("PRIVATE-SYNTHETIC-SECRET", json.dumps(result))
        self.assertTrue(self.engine.created and self.engine.removed)
        self.assertFalse(self.engine.up)
        differences = result["difference_proposal"]["changes"]
        self.assertNotIn("/HostConfig/OomKillDisable", [item["path"] for item in differences])
        self.assertIn("/Config/Labels/com.docker.compose.version", [item["path"] for item in differences])
        self.assertEqual(result["owned_created_service_count"], 1)
        self.assertEqual(len(self.engine.removed_ids), 1)
        create = [argv for argv in self.engine.calls if "up" in argv and "--no-start" in argv]
        self.assertEqual(len(create), 1)
        self.assertIn("--no-deps", create[0])
        self.assertFalse(any("--no-interpolate" in argv for argv in self.engine.calls))

    def test_same_actual_plan_and_reviewed_fingerprints_verify_without_activation(self):
        proposal = json.dumps(self.observe()["difference_proposal"]).encode()
        self.engine.created = self.engine.removed = False
        self.plan["action"] = "probe_only"
        result = self.observe(proposal)
        self.assertTrue(result["reviewed_diff_verified"])
        self.assertFalse(result["applied"])
        self.assertFalse(self.engine.up)

    def test_actual_file_drift_and_forged_supplied_snapshot_fail_before_create(self):
        self.engine.env.write_text("SYNTHETIC=changed\n")
        with self.assertRaises(ValueError):
            self.observe()
        self.assertFalse(self.engine.created)
        self.plan["proposed"] = copy.deepcopy(self.engine.running)
        with self.assertRaises(ValueError):
            self.observe()

    def test_drift_after_probe_prevents_bound_apply(self):
        proposal = json.dumps(self.observe()["difference_proposal"]).encode()
        self.engine.created = self.engine.removed = False
        self.engine.mutate_after_create = True
        self.plan.update(action="activate_management", freeze_receipt_sha256="4" * 64)
        with self.assertRaises(driver.OperationFailure) as failure:
            self.observe(proposal)
        self.assertEqual(failure.exception.status["stage"], "pre-mutation")
        self.assertFalse(failure.exception.status["up_executed"])
        self.assertFalse(self.engine.up)
        self.assertTrue(self.engine.removed)

    def test_unknown_metadata_and_wrong_actual_engine_health_cannot_be_asserted_away(self):
        self.engine.unexpected_label = True
        with self.assertRaises(ValueError):
            self.observe()
        self.assertTrue(self.engine.removed)
        self.engine.created = self.engine.removed = self.engine.unexpected_label = False
        self.engine.health_override = ["CMD", "/healthcheck"]
        with self.assertRaises(ValueError):
            self.observe()
        self.assertFalse(self.engine.up)

    def test_failed_bound_management_recreate_runs_once_and_keeps_recovery_holds(self):
        proposal = json.dumps(self.observe()["difference_proposal"]).encode()
        self.engine.created = self.engine.removed = False
        self.plan.update(action="activate_management", freeze_receipt_sha256="4" * 64)
        with self.assertRaises(driver.OperationFailure) as failure:
            self.observe(proposal)
        self.assertEqual(failure.exception.status["stage"], "up-failed")
        self.assertTrue(failure.exception.status["up_executed"])
        self.assertFalse(failure.exception.status["up_succeeded"])
        self.assertFalse(failure.exception.status["automatic_rollback"])
        up = [argv for argv in self.engine.calls if "up" in argv and "--no-start" not in argv and "--help" not in argv]
        self.assertEqual(len(up), 1)
        self.assertEqual(up[0][up[0].index("up"):], ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "--wait", "--wait-timeout", "120", "coolify"])
        self.assertNotIn("down", json.dumps(self.engine.calls))

    def test_wrong_independent_plan_digest_does_not_touch_docker(self):
        raw = json.dumps(self.plan).encode()
        before = len(self.engine.calls)
        with self.assertRaises(ValueError):
            driver.observe(raw, expected_plan_sha256="0" * 64, operator_state_dir=self.state, runner=self.engine.run)
        self.assertEqual(len(self.engine.calls), before)

    def test_private_state_requires_trusted_nonreplaceable_ancestry(self):
        driver.trusted_state_directory(self.state)
        self.directory.chmod(0o777)
        with self.assertRaises(ValueError):
            driver.trusted_state_directory(self.state)
        self.directory.chmod(0o700)
        with patch.object(driver.os, "geteuid", return_value=os.geteuid() + 12345):
            with self.assertRaises(ValueError):
                driver.trusted_state_directory(self.state)

    def test_actual_runner_controls_compose_scope_and_wait_timeout(self):
        result = type("Result", (), {"returncode": 0, "stdout": b""})()
        with patch.dict(os.environ, {"COMPOSE_REMOVE_ORPHANS": "true"}), patch.object(driver.subprocess, "run", return_value=result) as run:
            driver.local_run(["docker", "compose", "up", "--wait-timeout", "120", "coolify"])
            self.assertEqual(run.call_args.kwargs["env"]["COMPOSE_REMOVE_ORPHANS"], "false")
            self.assertGreater(run.call_args.kwargs["timeout"], 120)

    def test_partial_creation_before_target_id_is_discovered_and_cleaned(self):
        self.engine.partial_create_failure = True
        with self.assertRaises(ValueError):
            self.observe()
        self.assertTrue(self.engine.removed)
        self.assertEqual(len(self.engine.removed_ids), 1)
        self.assertNotIn(self.engine.running_id, self.engine.removed_ids)

    def test_unsupported_actual_create_help_fails_before_creation(self):
        self.engine.create_help = b"--pull policy\n"
        with self.assertRaises(ValueError):
            self.observe()
        self.assertFalse(self.engine.created)

    def test_unknown_dependency_owner_preserves_entire_disposable_set(self):
        self.engine.unsafe_stub = True
        with self.assertRaises(ValueError):
            self.observe()
        self.assertFalse(self.engine.removed_ids)
        self.assertEqual(len(self.engine.rows), 2)

    def test_successful_apply_checks_exact_old_name_label_and_http200(self):
        proposal = json.dumps(self.observe()["difference_proposal"]).encode()
        self.engine.created = self.engine.removed = False
        self.engine.fail_up = False
        self.plan.update(action="activate_management", freeze_receipt_sha256="4" * 64)
        result = self.observe(proposal)
        self.assertTrue(result["applied"])
        self.assertEqual(result["application_http_status"], 200)
        self.assertEqual(self.engine.installed["Config"]["Labels"][driver.PREFIX + "replace"], "coolify")

    def test_wrong_replacement_name_and_redirect_cannot_pass_post_apply(self):
        proposal = json.dumps(self.observe()["difference_proposal"]).encode()
        self.engine.created = self.engine.removed = False
        self.engine.fail_up = False
        self.engine.wrong_replace = True
        self.plan.update(action="activate_management", freeze_receipt_sha256="4" * 64)
        with self.assertRaises(driver.OperationFailure) as failure:
            self.observe(proposal)
        state = failure.exception.status
        self.assertEqual(state["stage"], "post-up-contract-mismatch")
        self.assertTrue(state["up_executed"] and state["up_succeeded"])
        self.assertEqual(state["application_http_status"], 200)
        self.assertEqual(state["installed_container_id"], "e" * 64)
        self.assertRegex(state["post_up_inspect_sha256"], r"^[0-9a-f]{64}$")
        persisted = json.loads((self.state / state["private_operation_state_id"] / "operation-status.json").read_bytes())
        self.assertEqual(persisted["stage"], state["stage"])
        self.assertNotIn("PRIVATE-SYNTHETIC-SECRET", json.dumps(persisted))
        self.assertTrue((self.state / state["private_operation_state_id"] / "post-up-inspect.json").is_file())
        self.engine.created = self.engine.removed = self.engine.wrong_replace = False
        self.engine.http_status = b"302"
        with self.assertRaises(driver.OperationFailure) as failure:
            self.observe(proposal)
        state = failure.exception.status
        self.assertEqual(state["stage"], "http-failed")
        self.assertEqual(state["application_http_status"], 302)
        self.assertTrue(state["up_executed"] and state["up_succeeded"])
        self.assertFalse(state["automatic_rollback"] or state["automatic_retry"])

    def test_wrong_old_identity_or_name_and_unreviewed_compose_version_fail(self):
        self.engine.running["Name"] = "/wrong-old-name"
        with self.assertRaises(ValueError):
            self.observe()

        self.engine.running["Name"] = "/coolify"
        self.engine.running["Id"] = "f" * 64
        with self.assertRaises(ValueError):
            self.observe()
        self.engine.running["Id"] = self.engine.running_id
        self.engine.version = b"5.6.2\n"
        self.plan["expected_chain_ticket"], _ = capture_chain([self.engine.compose], self.engine.env, "source", "coolify", self.engine.run)
        with self.assertRaises(ValueError):
            self.observe()

    def test_independently_selected_platform_and_probe_label_must_agree(self):
        self.engine.bad_selected_platform = True
        with self.assertRaises(ValueError):
            self.observe()
        self.assertFalse(self.engine.created)
        self.engine.bad_selected_platform = False
        self.engine.wrong_image_label = True
        with self.assertRaises(ValueError):
            self.observe()
        self.assertFalse(self.engine.up)


if __name__ == "__main__":
    unittest.main()
