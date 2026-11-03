"""Pure synthetic tests; no Docker calls, production files or network writes."""

import copy
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

import compose_contract_projection as projection


def fixtures():
    mounts = [{"type": "bind", "source": f"/synthetic/source{index}", "target": f"/synthetic/target{index}",
               "read_only": index == 0, "bind": {"create_host_path": True}} for index in range(7)]
    service = {"image": "sha256:" + "1" * 64, "environment": {"SYNTHETIC": "literal$$secret"},
               "container_name": "coolify", "depends_on": {"redis": {"condition": "service_healthy", "required": True}},
               "command": ["/init"], "entrypoint": None, "working_dir": "/var/www/html", "restart": "unless-stopped",
               "healthcheck": {"test": ["CMD", "true"]}, "extra_hosts": ["host.docker.internal:host-gateway"],
               "pull_policy": "never", "expose": ["8000"],
               "ports": [{"target": 8080, "published": "8000", "host_ip": "0.0.0.0", "protocol": "tcp", "mode": "ingress"}],
               "volumes": mounts, "networks": {"coolify": {"aliases": ["coolify-realtime"]}}}
    host = {"NetworkMode": "coolify", "Binds": [f'{item["source"]}:{item["target"]}:{"ro" if item["read_only"] else "rw"}' for item in mounts],
            "PortBindings": {"8080/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8000"}]}, "OomKillDisable": None,
            **{f"SyntheticHostConfigField{index}": None for index in range(59)}}
    running = {"Id": "a" * 64, "Name": "/coolify", "Config": {"Env": ["SYNTHETIC=literal$secret"], "Volumes": None,
               "ExposedPorts": {"8080/tcp": {}, "8000/tcp": {}}, "SyntheticConfig": "unchanged"}, "HostConfig": host,
               "Mounts": [{"Type": "bind", "Source": item["source"], "Destination": item["target"],
                           "RW": not item["read_only"], "Propagation": "rprivate"} for item in mounts],
               "NetworkSettings": {"Networks": {"coolify": {"Aliases": ["coolify", "coolify", "coolify-realtime"],
                   "IPAddress": "192.0.2.10", "GlobalIPv6Address": "2001:db8::10", "IPAMConfig": None,
                   "MacAddress": "02:00:00:00:00:10", "DriverOpts": None, "Links": None}}}}
    probe = copy.deepcopy(running)
    probe.update(Id="b" * 64, Name="/owned-probe", State={"Status": "created", "Running": False, "Pid": 0}, Mounts=[])
    probe["HostConfig"].update(NetworkMode="none", Binds=[], PortBindings={})
    probe["NetworkSettings"] = {"Networks": {"none": {}}}
    definitions = {"coolify": {"name": "coolify", "external": True}}
    image = {"ExposedPorts": {"8080/tcp": {}}, "Volumes": None}
    return running, probe, service, copy.deepcopy(service), definitions, image, copy.deepcopy(image)


class ProjectionTests(unittest.TestCase):
    def test_docker_environment_replaces_all_compose_controls_and_preserves_application_values(self):
        inherited = {"COMPOSE_REMOVE_ORPHANS": "true", "COMPOSE_IGNORE_ORPHANS": "true",
                     "COMPOSE_UNKNOWN_FUTURE_FLAG": "unsafe", "COMPOSE_FILE": "/unreviewed/compose.yml",
                     "COMPOSE_PROJECT_NAME": "unreviewed", "COMPOSE_PROFILES": "unreviewed",
                     "SYNTHETIC_APP_SECRET": "literal$private\nvalue", "DOCKER_CONTEXT": "trusted-context",
                     "PATH": "/synthetic/bin"}
        expected_policy = {"COMPOSE_REMOVE_ORPHANS": "false", "COMPOSE_IGNORE_ORPHANS": "false",
                           "COMPOSE_CONVERT_WINDOWS_PATHS": "false", "COMPOSE_COMPATIBILITY": "false",
                           "COMPOSE_PROFILES": "", "COMPOSE_MENU": "false", "COMPOSE_ANSI": "never",
                           "COMPOSE_PROGRESS": "quiet"}
        with patch.dict(os.environ, inherited, clear=True):
            actual = projection.controlled_docker_environment()
            self.assertEqual(dict(os.environ), inherited)
        self.assertEqual({key: value for key, value in actual.items() if key.startswith("COMPOSE_")}, expected_policy)
        for key in ("SYNTHETIC_APP_SECRET", "DOCKER_CONTEXT", "PATH"):
            self.assertEqual(actual[key], inherited[key])

    def test_read_only_runner_uses_the_same_controlled_environment_without_docker_calls(self):
        result = subprocess.CompletedProcess([], 0, stdout=b"synthetic result")
        with patch.dict(os.environ, {"COMPOSE_REMOVE_ORPHANS": "true", "COMPOSE_NEW_FLAG": "unsafe",
                                     "SYNTHETIC_APP_SECRET": "unchanged$secret"}), \
                patch.object(projection.subprocess, "run", return_value=result) as run:
            self.assertEqual(projection._read_only_run(["docker", "compose", "version", "--short"]), b"synthetic result")
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["COMPOSE_REMOVE_ORPHANS"], "false")
        self.assertNotIn("COMPOSE_NEW_FLAG", environment)
        self.assertEqual(environment["SYNTHETIC_APP_SECRET"], "unchanged$secret")

    def test_ordinary_unchanged_network_and_seven_binds_pass_without_pins(self):
        args = fixtures()
        output = projection.prove_and_reinsert(*args)
        self.assertEqual(output["Mounts"], args[0]["Mounts"])
        self.assertEqual(output["NetworkSettings"], args[0]["NetworkSettings"])
        self.assertIsNone(output["NetworkSettings"]["Networks"]["coolify"]["IPAMConfig"])
        self.assertNotIn("mac_address", args[3]["networks"]["coolify"])
        self.assertEqual(len(output["HostConfig"]), 63)

    def test_existing_mac_pin_is_optional_but_must_preserve_exact_current_mac(self):
        args = fixtures()
        args[3]["networks"]["coolify"]["mac_address"] = "02:00:00:00:00:10"
        projection.prove_and_reinsert(*args)
        projection.prove_and_reinsert(*args, endpoint_mode="existing_mac")
        args[3]["networks"]["coolify"]["mac_address"] = "02:00:00:00:00:11"
        with self.assertRaises(ValueError):
            projection.prove_and_reinsert(*args)
        with self.assertRaises(ValueError):
            projection.prove_and_reinsert(*fixtures(), endpoint_mode="existing_mac")

    def test_existing_declared_ipam_is_preserved_but_new_static_pins_are_not_invented(self):
        args = fixtures()
        for service in args[2:4]:
            service["networks"]["coolify"].update(ipv4_address="192.0.2.10", ipv6_address="2001:db8::10")
        args[0]["NetworkSettings"]["Networks"]["coolify"]["IPAMConfig"] = {"IPv4Address": "192.0.2.10", "IPv6Address": "2001:db8::10"}
        projection.prove_and_reinsert(*args)
        args = fixtures()
        args[3]["networks"]["coolify"]["ipv4_address"] = "192.0.2.10"
        with self.assertRaises(ValueError):
            projection.prove_and_reinsert(*args)

    def test_all_other_engine_fields_and_oom_default_change_survive_for_final_comparison(self):
        args = fixtures()
        args[1]["HostConfig"]["OomKillDisable"] = False
        args[1]["HostConfig"]["SyntheticHostConfigField58"] = "changed"
        args[1]["Config"]["SyntheticConfig"] = "changed"
        output = projection.prove_and_reinsert(*args)
        self.assertIs(output["HostConfig"]["OomKillDisable"], False)
        self.assertEqual(output["HostConfig"]["SyntheticHostConfigField58"], "changed")
        self.assertEqual(output["Config"]["SyntheticConfig"], "changed")
        self.assertEqual(len(output["HostConfig"]), 63)
        self.assertIsNone(args[0]["HostConfig"]["OomKillDisable"])

    def test_recipe_preserves_dependencies_and_every_unmodified_service_field(self):
        service = fixtures()[2]
        service.update(read_only=True, cap_drop=["ALL"], user="9999:9999", labels={"synthetic": "value"}, pull_policy="always")
        output = projection.safe_recipe(service, None, "1" * 32)
        changed = {"networks", "network_mode", "ports", "volumes", "container_name", "labels"}
        for key in set(service) - changed:
            self.assertEqual(output[key], service[key])
        self.assertEqual(output["depends_on"], service["depends_on"])
        self.assertEqual(output["labels"]["synthetic"], "value")
        self.assertEqual(output["labels"][projection.OWNER_LABEL], "1" * 32)
        self.assertEqual((output["network_mode"], output["ports"], output["volumes"]), ("none", [], []))
        self.assertNotIn(projection.OWNER_LABEL, service["labels"])

    def test_recipe_unknown_fields_image_volumes_logging_and_ownership_reject(self):
        for mutate in (lambda s: s.update(post_start=[{"command": "unsafe"}]),
                       lambda s: s.update(logging={"driver": "remote-plugin"}),
                       lambda s: s.update(labels={projection.OWNER_LABEL: "previous-owner"}),
                       lambda s: s.update(environment={"SYNTHETIC": "unescaped$variable"})):
            service = fixtures()[2]
            mutate(service)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                projection.safe_recipe(service, None, "1" * 32)
        with self.assertRaises(ValueError):
            projection.safe_recipe(fixtures()[2], {"/anonymous": {}}, "1" * 32)

    def test_port_mount_alias_and_ip_changes_cannot_be_reinserted(self):
        mutations = [lambda x: x[3]["ports"][0].update(published="6001"),
                     lambda x: x[3]["volumes"][0].update(source="/synthetic/other"),
                     lambda x: x[3]["networks"]["coolify"].update(aliases=["other"]),
                     lambda x: x[3]["networks"]["coolify"].update(ipv6_address="2001:db8::20"),
                     lambda x: x[0]["HostConfig"]["PortBindings"]["8080/tcp"][0].update(HostPort="6002"),
                     lambda x: x[0]["HostConfig"]["Binds"].__setitem__(0, "/other:/synthetic/target0:ro"),
                     lambda x: x[0]["Mounts"][0].update(RW=True),
                     lambda x: x[6].update(ExposedPorts={"9999/tcp": {}})]
        for mutate in mutations:
            args = fixtures()
            mutate(args)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                projection.prove_and_reinsert(*args)

    def test_duplicate_alias_count_order_driver_options_and_link_local_are_proved(self):
        for mutate in (lambda e: e.update(Aliases=["coolify", "coolify-realtime"]),
                       lambda e: e.update(Aliases=["coolify-realtime", "coolify", "coolify"]),
                       lambda e: e.update(DriverOpts={"unreviewed": "option"}),
                       lambda e: e.update(IPAMConfig={"LinkLocalIPs": ["fe80::10"]}),
                       lambda e: e.update(UnexpectedEndpointField=True)):
            args = fixtures()
            mutate(args[0]["NetworkSettings"]["Networks"]["coolify"])
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                projection.prove_and_reinsert(*args)

    def test_disconnected_probe_must_never_have_started_or_acquired_connectivity(self):
        for mutate in (lambda p: p["State"].update(Status="exited"),
                       lambda p: p["State"].update(Running=True),
                       lambda p: p["State"].update(Pid=1),
                       lambda p: p["HostConfig"].update(NetworkMode="coolify"),
                       lambda p: p["HostConfig"].update(Binds=["/production:/data:rw"]),
                       lambda p: p["HostConfig"].update(PublishAllPorts=True),
                       lambda p: p["Config"].update(Volumes={"/anonymous": {}})):
            args = fixtures()
            mutate(args[1])
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                projection.prove_and_reinsert(*args)

    def test_random_range_duplicate_and_unsupported_ports_or_mounts_reject(self):
        for port in ({"target": 8080}, {"target": 8080, "published": "0"},
                     {"target": 8080, "published": "8000-8001"},
                     {"target": 8080, "published": "8000", "app_protocol": "http"}):
            with self.subTest(port=port), self.assertRaises(ValueError):
                projection.ports({"ports": [port]})
        for mount in ({"type": "volume", "source": "named", "target": "/data"},
                      {"type": "bind", "source": "./relative", "target": "/data"},
                      {"type": "bind", "source": "/path$$ambiguous", "target": "/data"},
                      {"type": "bind", "source": "/data", "target": "/data", "bind": {"selinux": "z"}}):
            with self.subTest(mount=mount), self.assertRaises(ValueError):
                projection.bind_mounts({"volumes": [mount]})


class ChainTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="coolify-chain-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.files = [self.directory / "base.json", self.directory / "override.json"]
        self.env = self.directory / ".env"
        self.env.write_text("SYNTHETIC=private-fixture\n")
        for index, path in enumerate(self.files):
            path.write_text(json.dumps({"synthetic": index}))
        self.rendered = {"services": {"coolify": fixtures()[2]}}
        self.version, self.service_hash, self.calls = b"5.6.1\n", b"coolify " + b"a" * 64 + b"\n", []

    def runner(self, argv):
        self.calls.append(argv)
        if "--format" in argv:
            return json.dumps(self.rendered).encode()
        if "--hash" in argv:
            return self.service_hash
        return self.version

    def capture(self):
        return projection.capture_chain(self.files, self.env, "source", "coolify", self.runner)

    def recheck(self, ticket):
        return projection.recheck_chain(ticket, self.files, self.env, "source", "coolify", self.runner)

    def test_actual_ordered_chain_project_directory_hash_and_version_are_bound(self):
        with patch.object(projection.subprocess, "run") as process:
            ticket, rendered = self.capture()
        process.assert_not_called()
        self.assertEqual(rendered, self.rendered)
        self.assertEqual([item["path"] for item in ticket["chain"]], list(map(str, [self.env, *self.files])))
        self.assertNotIn("private-fixture", json.dumps(ticket))
        self.assertEqual(ticket["project_directory"], str(self.files[0].parent))
        for argv in self.calls[:2]:
            self.assertEqual(argv[argv.index("--project-directory") + 1], str(self.files[0].parent))
            self.assertNotIn("--no-interpolate", argv)
            self.assertEqual([argv[i + 1] for i, value in enumerate(argv) if value == "-f"], list(map(str, self.files)))
        self.recheck(ticket)

    def test_source_env_order_render_ambient_hash_and_version_drift_reject(self):
        for field in ("env", "file", "order", "ambient", "hash", "version"):
            ticket, _ = self.capture()
            old_files, old_rendered = self.files[:], copy.deepcopy(self.rendered)
            old_env, old_file = self.env.read_bytes(), self.files[0].read_bytes()
            old_hash, old_version = self.service_hash, self.version
            if field == "env":
                self.env.write_text("SYNTHETIC=changed\n")
            elif field == "file":
                self.files[0].write_text("changed bytes\n")
            elif field == "order":
                self.files.reverse()
            elif field == "ambient":
                self.rendered["services"]["coolify"]["environment"]["SYNTHETIC"] = "changed ambient value"
            elif field == "hash":
                self.service_hash = b"coolify " + b"b" * 64
            else:
                self.version = b"2.38.2"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.recheck(ticket)
            self.files, self.rendered = old_files, old_rendered
            self.env.write_bytes(old_env)
            self.files[0].write_bytes(old_file)
            self.service_hash, self.version = old_hash, old_version

    def test_chain_changes_during_actual_queries_reject(self):
        def runner(argv):
            result = self.runner(argv)
            if "--hash" in argv:
                self.files[0].write_text("changed during actual observation\n")
            return result
        with self.assertRaises(ValueError):
            projection.capture_chain(self.files, self.env, "source", "coolify", runner)

    def test_missing_relative_symlink_and_duplicate_chain_inputs_reject(self):
        for mode in ("relative", "duplicate", "symlink"):
            files = self.files[:]
            if mode == "relative":
                files[0] = Path("relative.json")
            elif mode == "duplicate":
                files.append(files[0])
            else:
                link = self.directory / "linked.json"
                link.symlink_to(files[0])
                files[0] = link
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                projection.capture_chain(files, self.env, "source", "coolify", self.runner)

    def test_unsupported_hash_and_version_output_reject(self):
        for field, value in (("version", b"unknown-plugin"), ("service_hash", b"caller-supplied-hash")):
            old = getattr(self, field)
            setattr(self, field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.capture()
            setattr(self, field, old)

    def test_project_env_compose_controls_reject_before_any_actual_query(self):
        for raw in (b"COMPOSE_REMOVE_ORPHANS=true\n", b" export COMPOSE_PROFILES=unsafe\r\n",
                    b"\tCOMPOSE_UNKNOWN_FUTURE_CONTROL: true\n", b"COMPOSE_REMOVE_ORPHANS\r\n",
                    b"'COMPOSE_MENU'=true\n", b'"COMPOSE_FILE"=/unreviewed.yml\n',
                    b"\xef\xbb\xbfCOMPOSE_UNKNOWN_FUTURE_CONTROL=true\n",
                    "\u00a0export\u00a0COMPOSE_UNKNOWN_FUTURE_CONTROL=true\n".encode()):
            self.env.write_bytes(raw)
            self.calls.clear()
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, "Compose controls in project env file are unsupported"):
                self.capture()
            self.assertFalse(self.calls)
            self.assertEqual(self.env.read_bytes(), raw)

    def test_project_env_application_values_and_comments_remain_unchanged(self):
        raw = "# COMPOSE_REMOVE_ORPHANS=true\nSYNTHETIC=literal$private\nOTHER='COMPOSE_FILE=/app/value'\nUNICODE=privat\u00e9\n".encode()
        self.env.write_bytes(raw)
        ticket, _ = self.capture()
        self.recheck(ticket)
        self.assertEqual(self.env.read_bytes(), raw)
        self.assertNotIn("literal$private", json.dumps(ticket))

    def test_ambiguous_dotenv_encoding_is_rejected_without_query_or_rewrite(self):
        raw = b"SYNTHETIC=\xffinvalid-encoding\n"
        self.env.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "unsupported project env file encoding"):
            self.capture()
        self.assertFalse(self.calls)
        self.assertEqual(self.env.read_bytes(), raw)

    def test_new_dotenv_compose_control_during_capture_is_rejected(self):
        def runner(argv):
            result = self.runner(argv)
            if "--hash" in argv:
                self.env.write_bytes(b"COMPOSE_REMOVE_ORPHANS=true\n")
            return result
        with self.assertRaisesRegex(ValueError, "Compose controls in project env file are unsupported"):
            projection.capture_chain(self.files, self.env, "source", "coolify", runner)


if __name__ == "__main__":
    unittest.main()
