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
from compose_contract_projection import capture_chain, digest
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
        if argv[:3] == ["docker", "compose", "version"]:
            return b"5.6.1\n"
        if argv[:2] == ["docker", "compose"]:
            path = Path(argv[argv.index("-f") + 1])
            rendered = json.loads(path.read_bytes())
            if "config" in argv:
                if "--hash" in argv:
                    return ("coolify " + digest(rendered["services"]["coolify"]) + "\n").encode()
                return json.dumps(rendered).encode()
            if "create" in argv:
                self.created = True
                safe = rendered["services"]["coolify"]
                if safe["network_mode"] != "none" or safe["ports"] or safe["volumes"]:
                    raise AssertionError("unsafe probe recipe")
                self.probe = copy.deepcopy(self.running)
                self.probe.update(Id=self.probe_id, Image=self.candidate, Name="/" + safe["container_name"],
                                  Mounts=[], State={"Status": "running" if self.probe_started else "created", "Running": self.probe_started, "Pid": 1 if self.probe_started else 0})
                self.probe["Config"].update(Hostname=self.probe_id[:12], Image=self.candidate,
                    Env=[key + "=" + value for key, value in safe["environment"].items()],
                    Healthcheck={"Test": self.health_override or safe["healthcheck"]["test"]})
                self.probe["HostConfig"].update(NetworkMode="none", Binds=[], PortBindings={}, OomKillDisable=False)
                self.probe["NetworkSettings"] = {"Ports": {}, "Networks": {"none": {}}}
                project = argv[argv.index("--project-name") + 1]
                generated = {"config-hash": digest(safe), "container-number": "1", "depends_on": "redis:service_healthy:false",
                    "image": self.candidate, "oneoff": "False", "project": project, "project.config_files": str(path),
                    "project.environment_file": "/dev/null", "project.working_dir": str(self.directory), "service": "coolify", "version": "5.6.1"}
                labels = {driver.PREFIX + key: value for key, value in generated.items()}
                labels.update(safe["labels"])
                if self.unexpected_label:
                    labels[driver.PREFIX + "unreviewed-future"] = "unexpected"
                self.probe["Config"]["Labels"] = labels
                if self.mutate_after_create:
                    self.env.write_text("SYNTHETIC=drift-after-create\n")
                return b""
            if "up" in argv:
                self.up = True
                raise ValueError("synthetic failed recreation; must never retry")
        if argv[:3] == ["docker", "image", "inspect"]:
            return json.dumps([{"Id": argv[3], "Config": self.image_config}]).encode()
        if argv[:2] == ["docker", "inspect"]:
            rows = [self.running if item == self.running_id else self.probe for item in argv[2:]]
            return json.dumps(rows).encode()
        if argv[:2] == ["docker", "ps"]:
            return ((self.probe_id if self.created and not self.removed else "") if "--all" in argv else self.running_id).encode()
        if argv[:2] == ["docker", "rm"]:
            self.removed = True
            return b""
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
        self.assertIn("/HostConfig/OomKillDisable", [item["path"] for item in differences])
        self.assertIn("/Config/Labels/com.docker.compose.version", [item["path"] for item in differences])
        self.assertTrue(any("--no-deps" in argv and "create" in argv for argv in self.engine.calls))
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
        with self.assertRaises(ValueError):
            self.observe(proposal)
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
        with self.assertRaises(ValueError):
            self.observe(proposal)
        up = [argv for argv in self.engine.calls if "up" in argv]
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


if __name__ == "__main__":
    unittest.main()
