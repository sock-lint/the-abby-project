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


def runtime_fixture():
    return {"Client": {"Version": "29.9.2", "ApiVersion": "1.56", "GitCommit": "a82e528",
                       "Os": "linux", "Arch": "amd64", "Context": "SYNTHETIC-PRIVATE-CONTEXT", "Experimental": None},
            "Server": {"Version": "29.9.2", "ApiVersion": "1.56", "Os": "linux", "Arch": "amd64",
                       "KernelVersion": "synthetic-private-kernel"}}


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

    def test_compose_561_empty_external_network_ipam_is_supported_without_address_changes(self):
        args = fixtures()
        args[4]["coolify"]["ipam"] = {}
        output = projection.prove_and_reinsert(*args)
        self.assertEqual(output["NetworkSettings"], args[0]["NetworkSettings"])
        self.assertIsNone(output["NetworkSettings"]["Networks"]["coolify"]["IPAMConfig"])
        for value in (None, [], {"driver": "default"}, {"config": []}, {"config": [{"subnet": "192.0.2.0/24"}]}):
            args[4]["coolify"]["ipam"] = value
            with self.subTest(ipam=value), self.assertRaises(ValueError):
                projection.prove_and_reinsert(*args)
        args[4]["coolify"]["ipam"] = {}
        args[4]["coolify"]["unknown_network_option"] = {}
        with self.assertRaises(ValueError):
            projection.prove_and_reinsert(*args)

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
        self.runtime = runtime_fixture()

    def runner(self, argv):
        self.calls.append(argv)
        if argv[:2] == ["docker", "version"]:
            return json.dumps(self.runtime).encode()
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

    def test_actual_docker_client_and_server_metadata_drift_invalidates_ticket(self):
        ticket, _ = self.capture()
        self.assertEqual(ticket["docker_runtime_version_sha256"], projection.digest(self.runtime))
        self.runtime["Client"]["Context"] = "different-private-context"
        with self.assertRaises(ValueError):
            self.recheck(ticket)
        self.runtime = runtime_fixture()
        self.runtime["Server"]["KernelVersion"] = "different-private-kernel"
        with self.assertRaises(ValueError):
            self.recheck(ticket)


class RuntimeSemanticsTests(unittest.TestCase):
    def runner(self, value):
        def run(argv):
            self.assertEqual(argv, ["docker", "version", "--format", "{{json .}}"])
            return json.dumps(value).encode()
        return run

    def test_current_tested_runtime_is_observed_and_private_client_context_is_hashed(self):
        value = runtime_fixture()
        proof = projection.observe_runtime(self.runner(value))
        self.assertEqual(proof["version_sha256"], projection.digest(value))
        self.assertEqual(proof["server"], {"Version": "29.9.2", "ApiVersion": "1.56", "Os": "linux", "Arch": "amd64"})
        self.assertNotIn("SYNTHETIC-PRIVATE-CONTEXT", json.dumps(proof))
        self.assertNotIn("synthetic-private-kernel", json.dumps(proof))

    def test_untested_client_server_api_platform_commit_and_experimental_mode_reject(self):
        for side, field, invalid in (("Client", "Version", "29.9.0"), ("Client", "ApiVersion", "1.55"),
                                     ("Client", "GitCommit", "unknown"), ("Client", "Os", "windows"),
                                     ("Client", "Arch", "arm64"), ("Client", "Experimental", True),
                                     ("Server", "Version", "29.9.0"), ("Server", "ApiVersion", "1.55"),
                                     ("Server", "Os", "windows"), ("Server", "Arch", "arm64")):
            value = runtime_fixture()
            value[side][field] = invalid
            with self.subTest(side=side, field=field), self.assertRaises(ValueError):
                projection.observe_runtime(self.runner(value))

    def test_expected_started_oom_default_changes_only_exact_false_to_none(self):
        projected = fixtures()[1]
        projected["HostConfig"]["OomKillDisable"] = False
        projected["HostConfig"]["SyntheticHostConfigField58"] = "must-remain-significant"
        proof = projection.observe_runtime(self.runner(runtime_fixture()))
        original = copy.deepcopy(projected)
        output = projection.model_expected_running_defaults(projected, fixtures()[3], proof)
        expected = copy.deepcopy(projected)
        expected["HostConfig"]["OomKillDisable"] = None
        self.assertEqual(output, expected)
        self.assertEqual(projected, original)
        self.assertEqual(len(output["HostConfig"]), 63)

    def test_oom_true_none_missing_explicit_settings_or_wrong_runtime_cannot_normalize(self):
        proof = projection.observe_runtime(self.runner(runtime_fixture()))
        for invalid in (True, None, 0, "false", "missing"):
            projected = fixtures()[1]
            if invalid == "missing":
                del projected["HostConfig"]["OomKillDisable"]
            else:
                projected["HostConfig"]["OomKillDisable"] = invalid
            with self.subTest(value=invalid), self.assertRaises(ValueError):
                projection.model_expected_running_defaults(projected, fixtures()[3], proof)
        projected = fixtures()[1]
        projected["HostConfig"]["OomKillDisable"] = False
        declared = fixtures()[3]
        declared["oom_kill_disable"] = False
        with self.assertRaises(ValueError):
            projection.model_expected_running_defaults(projected, declared, proof)
        invalid_proof = copy.deepcopy(proof)
        invalid_proof["server"]["Version"] = "29.9.0"
        with self.assertRaises(ValueError):
            projection.model_expected_running_defaults(projected, fixtures()[3], invalid_proof)
        projected["State"] = {"Status": "running", "Running": True, "Pid": 123}
        with self.assertRaises(ValueError):
            projection.model_expected_running_defaults(projected, fixtures()[3], proof)


class ImageSelectionTests(unittest.TestCase):
    def setUp(self):
        self.default_id = "sha256:" + "1" * 64
        self.selected_id = "sha256:" + "2" * 64
        self.default = {"Id": self.default_id, "Descriptor": {"mediaType": projection.OCI_INDEX, "digest": self.default_id, "size": 1234},
                        "Os": "linux", "Architecture": "amd64", "Config": {"Env": ["SECRET=PRIVATE-SYNTHETIC-IMAGE"], "User": "www-data"},
                        "RootFS": {"Type": "layers", "Layers": ["sha256:" + "3" * 64]}}
        self.selected = copy.deepcopy(self.default)
        self.selected.update(Id=self.selected_id, Descriptor={"mediaType": projection.OCI_MANIFEST, "digest": self.selected_id, "size": 5678})
        self.help = b"Options:\n      --platform string   Inspect a specific platform\n"
        self.calls = []

    def runner(self, argv):
        self.calls.append(argv)
        if argv[:2] == ["docker", "version"]:
            return json.dumps(runtime_fixture()).encode()
        if argv == ["docker", "image", "inspect", "--help"]:
            return self.help
        if argv == ["docker", "image", "inspect", self.default_id]:
            return json.dumps([self.default]).encode()
        if argv == ["docker", "image", "inspect", "--platform", "linux/amd64", self.default_id]:
            return json.dumps([self.selected]).encode()
        raise AssertionError("unexpected synthetic image query")

    def select(self, platform=None):
        return projection.selected_image_identity(copy.deepcopy(self.default), platform, self.runner)

    def test_index_uses_actual_selected_manifest_id_with_full_content_bound_and_no_private_receipt(self):
        selected, identity, evidence = self.select()
        self.assertEqual(selected, self.selected)
        self.assertEqual(identity, self.selected_id)
        self.assertNotEqual(identity, self.default_id)
        self.assertEqual(evidence["selection"], "index_to_manifest")
        self.assertNotIn("PRIVATE-SYNTHETIC-IMAGE", json.dumps(evidence))
        self.assertIn(["docker", "image", "inspect", "--platform", "linux/amd64", self.default_id], self.calls)

    def test_native_manifest_identity_must_remain_the_same(self):
        self.default["Descriptor"]["mediaType"] = projection.OCI_MANIFEST
        self.selected = copy.deepcopy(self.default)
        _, identity, evidence = self.select("linux/amd64")
        self.assertEqual(identity, self.default_id)
        self.assertEqual(evidence["selection"], "native_manifest")
        self.selected.update(Id=self.selected_id, Descriptor={"mediaType": projection.OCI_MANIFEST, "digest": self.selected_id})
        with self.assertRaises(ValueError):
            self.select()

    def test_unsupported_platform_missing_capability_or_ambiguous_descriptor_reject(self):
        for platform in ("linux/arm64", "windows/amd64", "linux/amd64/v2", ""):
            with self.subTest(platform=platform), self.assertRaises(ValueError):
                self.select(platform)
        self.help = b"Options without platform support\n"
        with self.assertRaises(ValueError):
            self.select()
        self.help = b" --platform string\n"
        for descriptor in (None, {}, {"mediaType": "unknown", "digest": self.default_id},
                           {"mediaType": projection.OCI_INDEX, "digest": self.selected_id}):
            self.default["Descriptor"] = descriptor
            with self.subTest(descriptor=descriptor), self.assertRaises(ValueError):
                self.select()

    def test_wrong_selected_platform_forged_digest_config_and_rootfs_changes_reject(self):
        original = copy.deepcopy(self.selected)
        for mutate in (lambda i: i.update(Architecture="arm64"), lambda i: i.update(Os="windows"),
                       lambda i: i["Descriptor"].update(digest=self.default_id),
                       lambda i: i["Descriptor"].update(mediaType=projection.OCI_INDEX),
                       lambda i: i["Config"].update(User="root"),
                       lambda i: i["RootFS"].update(Layers=["sha256:" + "4" * 64]),
                       lambda i: i["Descriptor"].update(platform={"os": "linux", "architecture": "arm64"})):
            self.selected = copy.deepcopy(original)
            mutate(self.selected)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                self.select()

    def test_default_supplied_json_cannot_replace_fresh_actual_image_observation(self):
        forged = copy.deepcopy(self.default)
        forged["Config"]["User"] = "root"
        with self.assertRaises(ValueError):
            projection.selected_image_identity(forged, None, self.runner)


if __name__ == "__main__":
    unittest.main()
