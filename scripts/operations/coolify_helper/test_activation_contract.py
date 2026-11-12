"""Synthetic drift, literal health encoding and realtime port collision checks."""

import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from verify_activation_contract import APPLICATION_TEST, COMPOSE_DEPENDENCIES_LABEL, check_port_collisions, compare, contract, differences, main, verify_health


def inspect_fixture():
    return {"Id": "a" * 64, "Image": "sha256:" + "1" * 64, "Path": "/init", "Args": [],
            "Config": {"Hostname": "a" * 12, "Env": ["SYNTHETIC=true"], "User": "www-data",
                       "Image": "sha256:" + "1" * 64, "Labels": {"synthetic": "true"},
                       "Healthcheck": {"Test": APPLICATION_TEST, "Interval": 30000000000}},
            "HostConfig": {"PortBindings": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18080"}]},
                           "Binds": ["synthetic:/data:ro"], "Privileged": False},
            "Mounts": [{"Type": "volume", "Source": "synthetic", "Destination": "/data", "RW": False}],
            "NetworkSettings": {"Networks": {"synthetic": {
                "Aliases": ["coolify"], "IPAMConfig": None, "DriverOpts": None,
                "IPAddress": "192.0.2.2", "EndpointID": "generated"}}, "Ports": {}},
            "State": {"Running": True}}


class ActivationContractTests(unittest.TestCase):
    def test_image_change_requires_exact_reviewed_before_and_after(self):
        before = inspect_fixture()
        after = copy.deepcopy(before)
        after["Image"] = "sha256:" + "2" * 64
        manifest = {"schema_version": 1, "changes": [{"path": "/Image", "before": contract(before)["Image"], "after": contract(after)["Image"]}]}
        compare(before, after, manifest)
        manifest["changes"][0]["before"] = "sha256:" + "3" * 64
        with self.assertRaises(ValueError):
            compare(before, after, manifest)

    def test_runtime_drift_outside_image_and_test_blocks(self):
        mutations = [lambda item: item["HostConfig"]["PortBindings"].update({"6001/tcp": [{"HostIp": "", "HostPort": "6001"}]}),
                     lambda item: item["Mounts"][0].update({"RW": True}),
                     lambda item: item["Config"]["Env"].append("PUSHER_BACKEND_PORT=6001"),
                     lambda item: item["NetworkSettings"]["Networks"]["synthetic"]["Aliases"].append("coolify-realtime"),
                     lambda item: item["Config"]["Healthcheck"].update({"Interval": 1}),
                     lambda item: item["Config"].update({"User": "root"}),
                     lambda item: item["HostConfig"].update({"Privileged": True}),
                     lambda item: item["NetworkSettings"]["Networks"]["synthetic"].update({"FutureCreationSetting": True})]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                before, after = inspect_fixture(), inspect_fixture()
                mutate(after)
                with self.assertRaises(ValueError):
                    compare(before, after, {"schema_version": 1, "changes": []})

    def test_static_addresses_remain_but_generated_addresses_do_not(self):
        before, after = inspect_fixture(), inspect_fixture()
        after["NetworkSettings"]["Networks"]["synthetic"]["IPAddress"] = "192.0.2.3"
        self.assertEqual(contract(before), contract(after))
        after["NetworkSettings"]["Networks"]["synthetic"]["IPAMConfig"] = {"IPv4Address": "192.0.2.3"}
        with self.assertRaises(ValueError):
            compare(before, after, {"schema_version": 1, "changes": []})

    def test_manifest_has_no_wildcard_or_duplicate_paths(self):
        for path in ("", "/Config/*"):
            with self.assertRaises(ValueError):
                compare(inspect_fixture(), inspect_fixture(), {"schema_version": 1, "changes": [{"path": path, "before": 1, "after": 2}]})

    def test_release_application_health_and_actual_engine_match(self):
        verify_health(APPLICATION_TEST, APPLICATION_TEST, APPLICATION_TEST, interpolated=True)
        for wrong in (["CMD", "/healthcheck"], ["CMD-SHELL", "true"]):
            with self.assertRaises(ValueError):
                verify_health(APPLICATION_TEST, APPLICATION_TEST, wrong, interpolated=True)

    def test_future_literal_dollar_is_encoded_and_decoded_once(self):
        expected = ["CMD-SHELL", 'test "$SYNTHETIC" = "$$literal"']
        encoded = [part.replace("$", "$$") for part in expected]
        verify_health(encoded, encoded, expected, interpolated=True, expected=expected)
        with self.assertRaises(ValueError):
            verify_health(expected, expected, expected, interpolated=False, expected=expected)
        with self.assertRaises(ValueError):
            verify_health(encoded, expected, expected, interpolated=True, expected=expected)
        with self.assertRaises(ValueError):
            verify_health(encoded, [part.replace("$", "$$") for part in encoded], expected, interpolated=True, expected=expected)

    def test_realtime_host_ports_block_even_with_different_container_port(self):
        proposed = inspect_fixture()
        proposed["HostConfig"]["PortBindings"] = {"6001/tcp": [{"HostIp": "0.0.0.0", "HostPort": "6001"}]}
        other = {"Id": "b" * 64, "State": {"Running": True},
                 "NetworkSettings": {"Ports": {"9000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6001"}]}}}
        with self.assertRaises(ValueError):
            check_port_collisions(proposed, [other], "a" * 64)
        other["NetworkSettings"]["Ports"] = {"6002/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6002"}]}
        proposed["HostConfig"]["PortBindings"] = {"6002/tcp": [{"HostIp": "::", "HostPort": "6002"}]}
        with self.assertRaises(ValueError):
            check_port_collisions(proposed, [other], "a" * 64)

    def test_old_management_owner_is_excluded_but_random_ports_rejected(self):
        proposed = inspect_fixture()
        check_port_collisions(proposed, [proposed], proposed["Id"])
        proposed["HostConfig"]["PortBindings"]["8080/tcp"][0]["HostPort"] = ""
        with self.assertRaises(ValueError):
            check_port_collisions(proposed, [], proposed["Id"])

    def test_incomplete_inventory_and_automatic_networking_block(self):
        with self.assertRaises(ValueError):
            check_port_collisions(inspect_fixture(), [{"Id": "partial"}], "a" * 64)
        for setting, value in (("NetworkMode", "host"), ("PublishAllPorts", True)):
            proposed = inspect_fixture()
            proposed["HostConfig"][setting] = value
            with self.assertRaises(ValueError):
                check_port_collisions(proposed, [], "a" * 64)

    def test_cli_requires_trusted_change_hash_and_never_prints_private_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            running, proposed = inspect_fixture(), inspect_fixture()
            proposed["Config"]["Env"] = ["SYNTHETIC=PRIVATE-SYNTHETIC-MARKER"]
            values = {"running": running, "proposed": proposed, "other-containers": [running],
                      "reviewed-changes": {"schema_version": 1, "changes": []},
                      "health-evidence": {"encoded": APPLICATION_TEST, "rendered": APPLICATION_TEST,
                                          "engine": APPLICATION_TEST, "interpolated": True}}
            args = []
            for name, value in values.items():
                path = directory / f"{name}.json"
                path.write_text(json.dumps(value))
                args.extend([f"--{name}", str(path)])
            digest = hashlib.sha256((directory / "reviewed-changes.json").read_bytes()).hexdigest()
            for expected in (digest, "0" * 64):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    status = main([*args, "--expected-changes-sha256", expected])
                self.assertEqual(status, 1)
                self.assertNotIn("PRIVATE-SYNTHETIC-MARKER", out.getvalue() + err.getvalue())
                self.assertNotIn(str(directory), out.getvalue() + err.getvalue())
            approved = {"schema_version": 1, "changes": [{"path": "/Config/Env/SYNTHETIC",
                        "before": contract(running)["Config"]["Env"]["SYNTHETIC"],
                        "after": contract(proposed)["Config"]["Env"]["SYNTHETIC"]}]}
            changes = directory / "reviewed-changes.json"
            changes.write_text(json.dumps(approved))
            digest = hashlib.sha256(changes.read_bytes()).hexdigest()
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                status = main([*args, "--expected-changes-sha256", digest])
            self.assertEqual(status, 0)
            self.assertNotIn("PRIVATE-SYNTHETIC-MARKER", out.getvalue() + err.getvalue())

    def test_order_only_environment_binds_mounts_and_aliases_pass(self):
        before = inspect_fixture()
        before["Config"]["Env"] = ["SYNTHETIC_A=one", "SYNTHETIC_B=two"]
        before["HostConfig"]["Binds"] = ["/synthetic/a:/a:ro", "/synthetic/b:/b:rw"]
        before["Mounts"].append({"Type": "bind", "Source": "/synthetic/b", "Destination": "/b", "RW": True})
        before["NetworkSettings"]["Networks"]["synthetic"]["Aliases"].append("synthetic-alias")
        after = copy.deepcopy(before)
        after["Config"]["Env"].reverse()
        after["HostConfig"]["Binds"].reverse()
        after["Mounts"].reverse()
        after["NetworkSettings"]["Networks"]["synthetic"]["Aliases"].reverse()
        compare(before, after, {"schema_version": 1, "changes": []})

    def test_value_drift_is_key_level_and_canonical_evidence_has_no_secret_values(self):
        before, after = inspect_fixture(), inspect_fixture()
        marker = "SYNTHETIC-SECRET-DO-NOT-EMIT"
        before["Config"].update(Env=[f"SECRET_TOKEN={marker}"], Cmd=["/bin/run", marker],
                                Labels={"test": marker})
        after["Config"] = copy.deepcopy(before["Config"])
        after["Config"]["Env"] = [f"SECRET_TOKEN={marker}-changed"]
        left, right = contract(before), contract(after)
        self.assertNotIn(marker, json.dumps(left))
        expected = {"schema_version": 1, "changes": [{"path": "/Config/Env/SECRET_TOKEN",
                    "before": left["Config"]["Env"]["SECRET_TOKEN"],
                    "after": right["Config"]["Env"]["SECRET_TOKEN"]}]}
        compare(before, after, expected)
        self.assertNotIn(marker, json.dumps(expected))
        with self.assertRaises(ValueError):
            compare(before, after, {"schema_version": 1, "changes": []})
        before["Config"]["Env"] *= 2
        with self.assertRaises(ValueError):
            contract(before)

    def test_generated_dependency_order_changes_pass_without_reviewed_difference(self):
        before, after = inspect_fixture(), inspect_fixture()
        before["Config"]["Labels"][COMPOSE_DEPENDENCIES_LABEL] = "redis:service_healthy:false,postgres:service_started:true"
        after["Config"]["Labels"][COMPOSE_DEPENDENCIES_LABEL] = "postgres:service_started:true,redis:service_healthy:false"
        compare(before, after, {"schema_version": 1, "changes": []})
        self.assertEqual(contract(before), contract(after))
        self.assertEqual(before["Config"]["Labels"][COMPOSE_DEPENDENCIES_LABEL], "redis:service_healthy:false,postgres:service_started:true")

    def test_generated_dependency_condition_restart_and_name_changes_remain_significant(self):
        before = inspect_fixture()
        before["Config"]["Labels"][COMPOSE_DEPENDENCIES_LABEL] = "redis:service_healthy:false,postgres:service_started:true"
        for value in ("postgres:service_started:true,redis:service_started:false",
                      "postgres:service_started:true,redis:service_healthy:true",
                      "postgres:service_started:true,redis-other:service_healthy:false"):
            after = copy.deepcopy(before)
            after["Config"]["Labels"][COMPOSE_DEPENDENCIES_LABEL] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare(before, after, {"schema_version": 1, "changes": []})

    def test_generated_dependency_duplicates_conflicts_and_malformed_records_reject(self):
        for value in ("redis:service_healthy:false,redis:service_healthy:false",
                      "redis:service_healthy:false,redis:service_started:true",
                      "redis:service_healthy", "redis:service_healthy:false:extra",
                      "redis:unknown_condition:false", "redis:service_healthy:False",
                      "redis:service_healthy:1", "redis:service_healthy:false,",
                      ",redis:service_healthy:false", "redis:service_healthy:false, postgres:service_started:true",
                      "bad/name:service_healthy:false", "redis\n:service_healthy:false", None, 123):
            value_object = inspect_fixture()
            value_object["Config"]["Labels"][COMPOSE_DEPENDENCIES_LABEL] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract(value_object)

    def test_empty_generated_dependency_label_and_completed_condition_are_valid(self):
        before = inspect_fixture()
        before["Config"]["Labels"][COMPOSE_DEPENDENCIES_LABEL] = ""
        compare(before, copy.deepcopy(before), {"schema_version": 1, "changes": []})
        before["Config"]["Labels"][COMPOSE_DEPENDENCIES_LABEL] = "_seed.job-1:service_completed_successfully:false"
        compare(before, copy.deepcopy(before), {"schema_version": 1, "changes": []})

    def test_only_generated_dependency_label_is_sorted_and_all_artifacts_hide_values(self):
        marker = "SYNTHETIC-SECRET-NAME-DO-NOT-EMIT"
        first = f"{marker}:service_healthy:false,redis:service_started:true"
        second = f"redis:service_started:true,{marker}:service_healthy:false"
        before, after = inspect_fixture(), inspect_fixture()
        before["Config"]["Labels"].update({COMPOSE_DEPENDENCIES_LABEL: first, "ordinary-label": first})
        after["Config"]["Labels"].update({COMPOSE_DEPENDENCIES_LABEL: second, "ordinary-label": second})
        left, right = contract(before), contract(after)
        actual = differences(left, right)
        self.assertEqual([item[0] for item in actual], ["/Config/Labels/ordinary-label"])
        approved = {"schema_version": 1, "changes": [{"path": path, "before": old, "after": new} for path, old, new in actual]}
        compare(before, after, approved)
        for artifact in (left, right, actual, approved):
            self.assertNotIn(marker, json.dumps(artifact))


if __name__ == "__main__":
    unittest.main()
