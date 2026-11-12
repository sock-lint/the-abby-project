"""Restricted Compose projection helpers for the trusted capture driver.

The driver must create, inspect and remove its own disconnected, never-started
probe. Supplied JSON alone is not provenance. These helpers do not create or
start containers, alter networks, write configuration, or authorize activation.
All errors are static; private rendered values are returned only to the driver.
"""

import copy
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess


SUPPORTED_SERVICE = {"image", "environment", "healthcheck", "container_name", "restart", "labels",
                     "depends_on", "ports", "volumes", "networks", "logging", "pull_policy", "command",
                     "entrypoint", "user", "working_dir", "expose", "read_only", "security_opt", "cap_add",
                     "cap_drop", "stop_grace_period", "stop_signal", "init", "extra_hosts", "hostname",
                     "domainname", "pids_limit", "mem_limit", "mem_reservation", "cpus", "shm_size",
                     "ulimits", "sysctls", "platform"}
OWNER_LABEL = "lol.bos.coolify-contract-probe.owner"
PROPAGATION = {"private", "rprivate", "shared", "rshared", "slave", "rslave"}
COMPOSE_CLIENT_POLICY = {
    "COMPOSE_REMOVE_ORPHANS": "false", "COMPOSE_IGNORE_ORPHANS": "false",
    "COMPOSE_CONVERT_WINDOWS_PATHS": "false", "COMPOSE_COMPATIBILITY": "false",
    "COMPOSE_PROFILES": "", "COMPOSE_MENU": "false", "COMPOSE_ANSI": "never",
    "COMPOSE_PROGRESS": "quiet",
}
TESTED_SERVER = {"Version": "29.9.3", "ApiVersion": "1.56", "Os": "linux", "Arch": "amd64",
                 "GitCommit": "70efc0e"}
TESTED_CLIENT = {**TESTED_SERVER, "GitCommit": "5457199"}
OCI_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"


def controlled_docker_environment():
    """Keep ordinary values, replace ambient Compose controls with this policy.

    The capture and action runners must both use this function. Explicit values
    also prevent Compose's dotenv loading from enabling these behavior flags.
    The selected project env file is separately rejected if it declares any
    Compose control key, including unknown future controls.
    """
    result = {key: value for key, value in os.environ.items() if not key.startswith("COMPOSE_")}
    result.update(COMPOSE_CLIENT_POLICY)
    return result


def _validate_client_env_file(raw):
    # Inspect encoding/key starts without interpreting, rewriting or exposing
    # application values. Ambiguous multiline values stop rather than guessing.
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("unsupported project env file encoding") from None
    if re.search(r'''(?m)^[^\S\r\n]*(?:export[^\S\r\n]+)?['"]?COMPOSE_''', text):
        raise ValueError("Compose controls in project env file are unsupported")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _read_only_run(argv):
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, check=False, timeout=30,
                                env=controlled_docker_environment())
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("actual Compose observation unavailable") from error
    if result.returncode:
        raise ValueError("actual Compose observation failed")
    return result.stdout


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate Compose JSON key")
        result[key] = value
    return result


def observe_runtime(runner=_read_only_run):
    """Bind actual Docker client/server metadata to the tested local semantics."""
    try:
        value = json.loads(runner(["docker", "version", "--format", "{{json .}}"]), object_pairs_hook=_unique_json)
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("actual Docker runtime metadata unavailable") from None
    if type(value) is not dict or type(value.get("Client")) is not dict or type(value.get("Server")) is not dict:
        raise ValueError("incomplete Docker runtime metadata")
    client, server = value["Client"], value["Server"]
    if (any(server.get(key) != expected for key, expected in TESTED_SERVER.items()) or
            server.get("Experimental") is not None and server.get("Experimental") is not False or
            any(client.get(key) != expected for key, expected in TESTED_CLIENT.items()) or
            client.get("Experimental") is not None or type(client.get("Context")) is not str or not client["Context"]):
        raise ValueError("unsupported Docker client or server runtime")
    # The owner-reviewed ticket also freezes the complete version response.
    identity = {key: client.get(key) for key in (*TESTED_CLIENT, "Context", "Experimental")}
    return {"schema_version": 1, "version_sha256": digest(value),
            "client_identity_sha256": digest(identity), "server": copy.deepcopy(TESTED_SERVER)}


def _runtime_proof(value):
    if (type(value) is not dict or set(value) != {"schema_version", "version_sha256", "client_identity_sha256", "server"} or
            type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["server"] != TESTED_SERVER or
            any(type(value[key]) is not str or not re.fullmatch(r"[0-9a-f]{64}", value[key]) for key in ("version_sha256", "client_identity_sha256"))):
        raise ValueError("unsupported actual Docker runtime proof")


def _one_image(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_unique_json)
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("actual image observation unavailable") from None
    if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
        raise ValueError("expected exactly one actual image")
    return value[0]


def _image_descriptor(image, media_type):
    descriptor = image.get("Descriptor")
    if (type(image.get("Id")) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", image["Id"]) or
            type(descriptor) is not dict or descriptor.get("mediaType") != media_type or descriptor.get("digest") != image["Id"] or
            image.get("Os") != "linux" or image.get("Architecture") != "amd64" or image.get("Variant") not in (None, "") or
            type(image.get("Config")) is not dict or type(image.get("RootFS")) is not dict):
        raise ValueError("unsupported image platform or OCI descriptor")
    if "platform" in descriptor:
        platform = descriptor["platform"]
        if (type(platform) is not dict or platform.get("os") != "linux" or platform.get("architecture") != "amd64" or
                platform.get("variant") not in (None, "")):
            raise ValueError("conflicting OCI descriptor platform")


def selected_image_identity(default_candidate, declared_platform, runner=_read_only_run):
    """Derive Compose's selected manifest identity from fresh actual CLI reads.

    The safe probe's label is never authority for its expected value. Full image
    Config and RootFS must agree across default and selected observations.
    """
    if declared_platform not in (None, "linux/amd64") or type(default_candidate) is not dict:
        raise ValueError("unsupported declared image platform")
    default_id = default_candidate.get("Id")
    if type(default_id) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", default_id):
        raise ValueError("immutable default image required")
    runtime = observe_runtime(runner)
    help_output = runner(["docker", "image", "inspect", "--help"])
    if type(help_output) is not bytes or re.search(rb"(?:^|\s)--platform(?:\s|=|$)", help_output) is None:
        raise ValueError("actual image inspect platform selection unavailable")
    actual_default = _one_image(runner(["docker", "image", "inspect", default_id]))
    if actual_default != default_candidate:
        raise ValueError("default image changed since actual observation")
    descriptor = actual_default.get("Descriptor")
    media_type = descriptor.get("mediaType") if type(descriptor) is dict else None
    if media_type not in (OCI_INDEX, OCI_MANIFEST):
        raise ValueError("unsupported default OCI image kind")
    _image_descriptor(actual_default, media_type)
    selected = _one_image(runner(["docker", "image", "inspect", "--platform", "linux/amd64", default_id]))
    _image_descriptor(selected, OCI_MANIFEST)
    if (selected["Config"] != actual_default["Config"] or selected["RootFS"] != actual_default["RootFS"] or
            (media_type == OCI_MANIFEST and selected["Id"] != default_id) or
            (media_type == OCI_INDEX and selected["Id"] == default_id)):
        raise ValueError("selected image identity or full creation content differs")
    evidence = {"schema_version": 1, "platform": "linux/amd64", "default_image_id": default_id,
                "selected_image_id": selected["Id"], "selection": "index_to_manifest" if media_type == OCI_INDEX else "native_manifest",
                "default_inspect_sha256": digest(actual_default), "selected_inspect_sha256": digest(selected),
                "inspect_platform_help_sha256": hashlib.sha256(help_output).hexdigest(),
                "docker_runtime_version_sha256": runtime["version_sha256"]}
    return selected, selected["Id"], evidence


def model_expected_running_defaults(projected, declared, runtimeProof):
    """Model only the observed 29.9.3 created-False to started-None OOM default.

    Actual root-owned disposable start/inspect proved this as the sole changed
    HostConfig key. This is an expected started contract, not normalization of
    installed observations, and no other fields are changed or ignored.
    """
    _runtime_proof(runtimeProof)
    _service(declared)
    if any(key in declared for key in ("oom_kill_disable", "oom_score_adj")):
        raise ValueError("explicit OOM settings unsupported")
    if type(projected) is not dict or type(projected.get("HostConfig")) is not dict or projected["HostConfig"].get("OomKillDisable") is not False:
        raise ValueError("unexpected created OOM default")
    state = projected.get("State", {})
    if state.get("Status") != "created" or state.get("Running") is not False or type(state.get("Pid")) is not int or state["Pid"] != 0:
        raise ValueError("expected never-started source for running-default model")
    result = copy.deepcopy(projected)
    result["HostConfig"]["OomKillDisable"] = None
    return result


def capture_chain(compose_files, env_file, project, service, runner=_read_only_run):
    """Bind ordered bytes to actual interpolated config/hash/version queries."""
    if (not isinstance(compose_files, (list, tuple)) or not 1 <= len(compose_files) <= 16 or
            not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", service)):
        raise ValueError("invalid Compose chain identity")
    compose_files = list(map(Path, compose_files))
    env_file = Path(env_file)
    paths = [env_file, *compose_files]
    if len(set(map(str, paths))) != len(paths):
        raise ValueError("duplicate Compose chain path")

    def snapshots():
        result = []
        for path in paths:
            if not path.is_absolute() or path.is_symlink() or not path.is_file():
                raise ValueError("chain requires absolute regular nonsymlink files")
            raw = path.read_bytes()
            if path == env_file:
                _validate_client_env_file(raw)
            result.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
        return result

    before = snapshots()
    project_directory = str(compose_files[0].parent)
    argv = ["docker", "compose", "--project-directory", project_directory,
            "--project-name", project, "--env-file", str(env_file)]
    for path in compose_files:
        argv += ["-f", str(path)]
    try:
        rendered_bytes = runner([*argv, "config", "--format", "json"])
        rendered = json.loads(rendered_bytes, object_pairs_hook=_unique_json)
        service_hash = runner([*argv, "config", "--hash", service]).decode().strip()
        version = runner(["docker", "compose", "version", "--short"]).decode().strip()
        runtime = observe_runtime(runner)
    except (UnicodeError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid actual Compose observation") from error
    if (type(rendered) is not dict or type(rendered.get("services")) is not dict or
            type(rendered["services"].get(service)) is not dict):
        raise ValueError("actual rendered service absent")
    if (re.fullmatch(re.escape(service) + r" [0-9a-f]{64}", service_hash) is None or
            re.fullmatch(r"v?[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9_.-]+)?", version) is None):
        raise ValueError("unsupported Compose hash or version output")
    if before != snapshots():
        raise ValueError("chain changed during observation")
    ticket = {"schema_version": 1, "chain": before, "project": project, "service": service,
              "project_directory": project_directory, "render_sha256": digest(rendered),
              "service_hash_output_sha256": hashlib.sha256(service_hash.encode()).hexdigest(),
              "compose_version_sha256": hashlib.sha256(version.encode()).hexdigest(),
              "docker_runtime_version_sha256": runtime["version_sha256"]}
    return ticket, rendered


def recheck_chain(expected, compose_files, env_file, project, service, runner=_read_only_run):
    actual, rendered = capture_chain(compose_files, env_file, project, service, runner)
    if actual != expected:
        raise ValueError("actual chain render or version differs from frozen ticket")
    return rendered


def _dollars(value):
    # Default interpolated Compose JSON escapes literal dollars once. Preserve
    # that encoding for the driver's next actual Compose render; never guess.
    if isinstance(value, dict):
        for key, item in value.items():
            _dollars(key)
            _dollars(item)
    elif isinstance(value, list):
        for item in value:
            _dollars(item)
    elif isinstance(value, str) and "$" in value.replace("$$", ""):
        raise ValueError("unsupported unescaped dollar in rendered service")


def _service(service):
    if type(service) is not dict or set(service) - SUPPORTED_SERVICE:
        raise ValueError("unsupported rendered service field")
    _dollars(service)


def safe_recipe(service, image_volumes, token):
    """Preserve dependencies and remaining settings in a disconnected recipe.

    The driver supplies harmless dummy dependencies and uses the supported
    up --no-start --no-deps path
    --pull never. The declared pull_policy remains available for comparison.
    This function never omits depends_on to make a comparison pass.
    """
    _service(service)
    if image_volumes:
        raise ValueError("image-declared volumes unsupported")
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("invalid ownership token")
    if type(service.get("logging", {})) is not dict or service.get("logging", {}).get("driver", "json-file") not in {"json-file", "local", "none"}:
        raise ValueError("unsupported logging plugin")
    ports(service)
    bind_mounts(service)
    result = copy.deepcopy(service)
    result.pop("networks", None)
    result.update(network_mode="none", ports=[], volumes=[],
                  container_name="coolify-contract-probe-" + token)
    labels = result.setdefault("labels", {})
    if type(labels) is not dict or OWNER_LABEL in labels:
        raise ValueError("invalid or preexisting ownership label")
    labels[OWNER_LABEL] = token
    return result


def ports(service):
    result = []
    items = service.get("ports", [])
    if type(items) is not list:
        raise ValueError("invalid published port declarations")
    for item in items:
        if type(item) is not dict or set(item) - {"mode", "target", "published", "protocol", "host_ip"}:
            raise ValueError("unsupported port option")
        if item.get("mode", "ingress") != "ingress" or item.get("protocol", "tcp") not in {"tcp", "udp"}:
            raise ValueError("unsupported port mode or protocol")
        target, published = str(item.get("target", "")), str(item.get("published", ""))
        if not all(re.fullmatch(r"[0-9]+", value) and 1 <= int(value) <= 65535 for value in (target, published)):
            raise ValueError("ambiguous random or ranged host port")
        address = item.get("host_ip", "0.0.0.0")
        try:
            canonical = str(ipaddress.ip_address(address)) if type(address) is str else None
        except ValueError as error:
            raise ValueError("invalid host bind address") from error
        if canonical != address:
            raise ValueError("noncanonical host bind address")
        result.append((target + "/" + item.get("protocol", "tcp"), address, published))
    if len(set(result)) != len(result):
        raise ValueError("duplicate published port declaration")
    return sorted(result)


def bind_mounts(service):
    result = []
    items = service.get("volumes", [])
    if type(items) is not list:
        raise ValueError("invalid bind mount declarations")
    for item in items:
        if type(item) is not dict or set(item) - {"type", "source", "target", "read_only", "bind"} or item.get("type") != "bind":
            raise ValueError("only explicit long syntax bind mounts supported")
        options = item.get("bind", {})
        if type(options) is not dict or set(options) - {"create_host_path", "propagation"}:
            raise ValueError("unsupported bind option")
        if (type(item.get("read_only", False)) is not bool or
                type(options.get("create_host_path", True)) is not bool or
                options.get("propagation", "rprivate") not in PROPAGATION):
            raise ValueError("invalid bind option")
        source, target = item.get("source"), item.get("target")
        if not all(type(path) is str and path.startswith("/") and not any(c in path for c in (":", "$", "\n", "\0")) for path in (source, target)):
            raise ValueError("ambiguous bind path")
        result.append((source, target, not item.get("read_only", False), options.get("propagation", "rprivate")))
    if len({item[1] for item in result}) != len(result):
        raise ValueError("duplicate mount destination")
    return sorted(result)


def _host_bind_mounts(host):
    result = []
    for binding in host.get("Binds") or []:
        if type(binding) is not str or len(binding.split(":")) != 3:
            raise ValueError("unsupported Engine bind encoding")
        source, target, flags = binding.split(":")
        options = flags.split(",")
        if (len(options) != len(set(options)) or set(options) - PROPAGATION - {"rw", "ro"} or
                len(set(options) & {"rw", "ro"}) != 1 or len(set(options) & PROPAGATION) > 1):
            raise ValueError("unsupported Engine bind flags")
        result.append((source, target, "ro" not in options, next(iter(set(options) & PROPAGATION), "rprivate")))
    for mount in host.get("Mounts") or []:
        if (type(mount) is not dict or mount.get("Type") != "bind" or
                set(mount) - {"Type", "Source", "Target", "ReadOnly", "BindOptions", "Consistency"}):
            raise ValueError("unsupported Engine mount request")
        options = mount.get("BindOptions") or {}
        if (set(options) - {"Propagation", "CreateMountpoint"} or
                options.get("Propagation", "rprivate") not in PROPAGATION or mount.get("Consistency", "") not in ("", "consistent")):
            raise ValueError("unsupported Engine bind request option")
        result.append((mount["Source"], mount["Target"], not mount.get("ReadOnly", False), options.get("Propagation", "rprivate")))
    return sorted(result)


def _exposure(image, service, published):
    result = copy.deepcopy(image.get("ExposedPorts") or {})
    if type(result) is not dict or any(value != {} for value in result.values()):
        raise ValueError("invalid image exposure")
    for item in service.get("expose", []):
        if not re.fullmatch(r"[0-9]+(?:/(?:tcp|udp))?", str(item)):
            raise ValueError("unsupported expose declaration")
        port = str(item) if "/" in str(item) else str(item) + "/tcp"
        if not 1 <= int(port.split("/")[0]) <= 65535:
            raise ValueError("unsupported expose port")
        result[port] = {}
    if published:
        result.update({port: {} for port, _, _ in ports(service)})
    return result


def _network(running, baseline, proposed, definitions, mode):
    old_networks, new_networks = baseline.get("networks"), proposed.get("networks")
    if (type(old_networks) is not dict or type(new_networks) is not dict or
            old_networks.keys() != new_networks.keys() or len(old_networks) != 1):
        raise ValueError("one unchanged explicit network is required")
    key = next(iter(old_networks))
    definition = definitions[key]
    if (type(definition) is not dict or not {"name", "external"} <= set(definition) or
            set(definition) - {"name", "external", "ipam"} or definition["external"] is not True or
            type(definition.get("ipam", {})) is not dict or definition.get("ipam", {}) != {}):
        raise ValueError("existing external network with explicit name required")
    name = definition["name"]
    if (set(running["NetworkSettings"]["Networks"]) != {name} or
            running["HostConfig"].get("NetworkMode") != name):
        raise ValueError("running network identity differs")
    endpoint = running["NetworkSettings"]["Networks"][name]
    allowed = {"NetworkID", "EndpointID", "Gateway", "IPAddress", "IPPrefixLen", "IPv6Gateway",
               "GlobalIPv6Address", "GlobalIPv6PrefixLen", "DNSNames", "IPAMConfig", "Links",
               "Aliases", "MacAddress", "DriverOpts", "GwPriority"}
    if set(endpoint) - allowed or endpoint.get("DriverOpts") or endpoint.get("Links") or endpoint.get("GwPriority", 0):
        raise ValueError("unsupported Engine endpoint setting")
    old, new = old_networks[key] or {}, new_networks[key] or {}
    fields = {"aliases", "ipv4_address", "ipv6_address", "mac_address"}
    if type(old) is not dict or type(new) is not dict or set(old) - fields or set(new) - fields:
        raise ValueError("unsupported declared endpoint setting")
    aliases = old.get("aliases", [])
    if type(aliases) is not list or any(type(alias) is not str for alias in aliases) or aliases != new.get("aliases", []):
        raise ValueError("declared alias drift")
    expected_aliases = [running["Name"].lstrip("/"), "coolify", *aliases]
    observed_aliases = [alias for alias in endpoint.get("Aliases") or [] if alias not in {running["Id"], running["Id"][:12]}]
    if observed_aliases != expected_aliases:
        raise ValueError("declared aliases do not match Engine sequence")
    requested_ipam = {}
    for field, observed, engine_key in (("ipv4_address", endpoint.get("IPAddress"), "IPv4Address"),
                                        ("ipv6_address", endpoint.get("GlobalIPv6Address"), "IPv6Address")):
        if old.get(field) != new.get(field):
            raise ValueError("declared IPAM drift")
        if field in old:
            try:
                canonical = str(ipaddress.ip_address(old[field]))
            except ValueError as error:
                raise ValueError("invalid declared IPAM") from error
            if old[field] != observed or canonical != old[field]:
                raise ValueError("baseline declared IPAM differs from Engine")
            requested_ipam[engine_key] = old[field]
    observed_ipam = endpoint.get("IPAMConfig") or {}
    if set(observed_ipam) - {"IPv4Address", "IPv6Address", "LinkLocalIPs"} or observed_ipam.get("LinkLocalIPs"):
        raise ValueError("additional endpoint addressing unsupported")
    if {key: value for key, value in observed_ipam.items() if value} != requested_ipam:
        raise ValueError("running requested IPAM differs from declaration")
    mac = endpoint.get("MacAddress")
    if (type(mac) is not str or not re.fullmatch(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", mac) or
            int(mac[:2], 16) & 1 or mac == "00:00:00:00:00:00"):
        raise ValueError("invalid existing endpoint MAC")
    if old.get("mac_address", mac) != mac:
        raise ValueError("baseline declared MAC differs from Engine")
    if mode not in {"unchanged_or_existing_mac", "existing_mac"}:
        raise ValueError("unsupported endpoint projection mode")
    if mode == "existing_mac" or new.get("mac_address") != old.get("mac_address"):
        if new.get("mac_address") != mac:
            raise ValueError("MAC pin must preserve exact existing MAC")


def prove_and_reinsert(running, probe, baseline_service, proposed_service, network_definition,
                       base_image_config, candidate_image_config, endpoint_mode="unchanged_or_existing_mac"):
    """Reinsert only connectivity independently proved against actual running.

    Every other Config/HostConfig field remains from the actual probe, including
    OomKillDisable and unknown future Engine fields. The final contract comparator
    must reject every difference outside its independently reviewed change set.
    """
    _service(baseline_service)
    _service(proposed_service)
    if (base_image_config.get("Volumes") or candidate_image_config.get("Volumes") or
            base_image_config.get("Volumes") != candidate_image_config.get("Volumes") or
            running["Config"].get("Volumes") or probe["Config"].get("Volumes")):
        raise ValueError("image or runtime declared volumes unsupported")
    if base_image_config.get("ExposedPorts") != candidate_image_config.get("ExposedPorts"):
        raise ValueError("image inherited exposure drift")
    if baseline_service.get("expose") != proposed_service.get("expose"):
        raise ValueError("declared exposure drift")
    if ((running["Config"].get("ExposedPorts") or {}) != _exposure(base_image_config, baseline_service, True) or
            (probe["Config"].get("ExposedPorts") or {}) != _exposure(candidate_image_config, proposed_service, False)):
        raise ValueError("actual exposure differs from declared and inherited exposure")
    state = probe.get("State", {})
    host = probe["HostConfig"]
    if (state.get("Status") != "created" or state.get("Running") is not False or
            type(state.get("Pid")) is not int or state["Pid"] != 0):
        raise ValueError("probe was started or state incomplete")
    if (host.get("NetworkMode") != "none" or any(host.get(key) for key in ("PortBindings", "Binds", "Mounts", "VolumesFrom", "PublishAllPorts")) or
            probe["Mounts"] or set(probe["NetworkSettings"]["Networks"]) - {"none"}):
        raise ValueError("probe is not disconnected and unmounted")
    declared_ports, declared_mounts = ports(baseline_service), bind_mounts(baseline_service)
    if declared_ports != ports(proposed_service) or declared_mounts != bind_mounts(proposed_service):
        raise ValueError("declared connectivity changed")
    observed_ports = sorted((key, item.get("HostIp") or "0.0.0.0", item["HostPort"])
                            for key, values in (running["HostConfig"].get("PortBindings") or {}).items() for item in values or [])
    observed_mounts = []
    for item in running["Mounts"]:
        if (item.get("Type") != "bind" or set(item) - {"Type", "Source", "Destination", "Mode", "RW", "Propagation"} or
                type(item.get("RW")) is not bool):
            raise ValueError("unsupported running mount")
        observed_mounts.append((item["Source"], item["Destination"], item["RW"], item.get("Propagation", "rprivate")))
    if (running["HostConfig"].get("VolumesFrom") or observed_ports != declared_ports or
            sorted(observed_mounts) != declared_mounts or _host_bind_mounts(running["HostConfig"]) != declared_mounts):
        raise ValueError("declared connectivity does not match running Engine")
    _network(running, baseline_service, proposed_service, network_definition, endpoint_mode)
    result = copy.deepcopy(probe)
    for field in ("PortBindings", "Binds", "Mounts", "NetworkMode"):
        if field in running["HostConfig"]:
            result["HostConfig"][field] = copy.deepcopy(running["HostConfig"][field])
        else:
            result["HostConfig"].pop(field, None)
    result["Config"]["ExposedPorts"] = copy.deepcopy(running["Config"].get("ExposedPorts"))
    result["Mounts"] = copy.deepcopy(running["Mounts"])
    result["NetworkSettings"] = copy.deepcopy(running["NetworkSettings"])
    return result
