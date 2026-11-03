"""Offline, fail-closed comparison of private Docker Engine inspect snapshots.

This does not translate Compose, inspect a host, change a container, or certify
that a supplied inventory is complete. The operator must obtain fresh snapshots
through the trusted route and independently approve the exact change file hash.
No configuration values are printed, including on failure.
"""

import argparse
import copy
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import sys


APPLICATION_TEST = ["CMD-SHELL", "curl --fail http://127.0.0.1:8080/api/health || exit 1"]
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def load_json(path):
    return json.loads(Path(path).read_text())


def single_inspect(value):
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if not isinstance(value, dict):
        raise ValueError("expected one Engine inspect object")
    for field in ("Id", "Image", "Path", "Args", "Config", "HostConfig", "Mounts", "NetworkSettings"):
        if field not in value:
            raise ValueError("incomplete Engine inspect snapshot")
    if not isinstance(value["Config"], dict) or not isinstance(value["HostConfig"], dict):
        raise ValueError("invalid Engine configuration")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", value["Image"]):
        raise ValueError("snapshot must identify an immutable image")
    if not isinstance(value["NetworkSettings"].get("Networks"), dict):
        raise ValueError("network snapshot missing")
    return value


def contract(value):
    """Keep all Config/HostConfig; omit only Engine-generated runtime identity.

    Requested static addresses remain in IPAMConfig; assigned addresses,
    endpoint IDs, gateway and generated DNSNames are not creation settings.
    MACs are retained conservatively because they can also be requested.
    Aliases are intentionally retained, including differences caused by a probe.
    Any such difference needs an exact reviewed change, never a wildcard ignore.
    """
    value = single_inspect(value)
    config = copy.deepcopy(value["Config"])
    environment = {}
    for entry in config.get("Env") or []:
        if not isinstance(entry, str) or "=" not in entry:
            raise ValueError("invalid environment entry")
        key, item = entry.split("=", 1)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or key in environment:
            raise ValueError("invalid or duplicate environment key")
        environment[key] = hashlib.sha256(item.encode()).hexdigest()
    config["Env"] = {}
    if config.get("Hostname") == value["Id"][:12]:
        config["Hostname"] = "<engine-generated-hostname>"
    networks = {}
    generated_endpoint_fields = {"NetworkID", "EndpointID", "Gateway", "IPAddress", "IPPrefixLen",
                                 "IPv6Gateway", "GlobalIPv6Address", "GlobalIPv6PrefixLen", "DNSNames"}
    for name, settings in value["NetworkSettings"]["Networks"].items():
        networks[name] = {key: copy.deepcopy(item) for key, item in settings.items()
                          if key not in generated_endpoint_fields}
    host_config = copy.deepcopy(value["HostConfig"])
    for field in ("Binds", "Mounts", "VolumesFrom", "CapAdd", "CapDrop", "SecurityOpt",
                  "GroupAdd", "Devices", "DeviceRequests", "Ulimits", "MaskedPaths", "ReadonlyPaths"):
        if isinstance(host_config.get(field), list):
            host_config[field] = sorted(host_config[field], key=lambda item: json.dumps(item, sort_keys=True))
    for bindings in (host_config.get("PortBindings") or {}).values():
        if isinstance(bindings, list):
            bindings.sort(key=lambda item: json.dumps(item, sort_keys=True))
    for settings in networks.values():
        for field in ("Aliases", "Links"):
            if isinstance(settings.get(field), list):
                settings[field] = sorted(settings[field])
    result = {"Image": value["Image"], "Path": value["Path"], "Args": value["Args"],
              "Config": config, "HostConfig": host_config,
              "Mounts": sorted(value["Mounts"], key=lambda item: json.dumps(item, sort_keys=True)),
              "Networks": networks}
    result = redact_strings(result)
    result["Config"]["Env"] = environment
    return result


def redact_strings(value):
    """Comparison artifacts contain no string values from private snapshots.

    Environment digests are installed separately after this function. Paths,
    labels and commands can contain secrets, so every string leaf is hashed.
    """
    if isinstance(value, dict):
        return {key: redact_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_strings(item) for item in value]
    if isinstance(value, str):
        return "sha256:" + hashlib.sha256(value.encode()).hexdigest()
    return value


def differences(before, after, path=""):
    if type(before) is not type(after):
        return [(path, before, after)]
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            escaped = key.replace("~", "~0").replace("/", "~1")
            child = f"{path}/{escaped}"
            if key not in before:
                result.append((child, {"absent": True}, after[key]))
            elif key not in after:
                result.append((child, before[key], {"absent": True}))
            else:
                result.extend(differences(before[key], after[key], child))
        return result
    return [] if before == after else [(path, before, after)]


def compare(before, after, changes):
    if (not isinstance(changes, dict) or set(changes) != {"schema_version", "changes"}
            or type(changes["schema_version"]) is not int or changes["schema_version"] != 1):
        raise ValueError("invalid exact-change manifest")
    approved = changes["changes"]
    if not isinstance(approved, list):
        raise ValueError("invalid exact-change list")
    paths = set()
    for item in approved:
        if not isinstance(item, dict) or set(item) != {"path", "before", "after"}:
            raise ValueError("invalid exact-change entry")
        path = item["path"]
        if not isinstance(path, str) or not path.startswith("/") or path in paths or any(c in path for c in "*?["):
            raise ValueError("invalid or duplicate exact-change path")
        paths.add(path)
    actual = [{"path": path, "before": old, "after": new}
              for path, old, new in differences(contract(before), contract(after))]
    if (json.dumps(sorted(actual, key=lambda item: item["path"]), sort_keys=True)
            != json.dumps(sorted(approved, key=lambda item: item["path"]), sort_keys=True)):
        raise ValueError("running/proposed contract differs from the exact reviewed change set")


def verify_health(encoded, rendered, engine, *, interpolated, expected=APPLICATION_TEST):
    """Default Compose JSON re-escapes literal dollars once; Engine does not."""
    if interpolated is not True:
        raise ValueError("an interpolated Compose render is required")
    if encoded != [part.replace("$", "$$") for part in expected]:
        raise ValueError("Compose source health test is not the approved literal encoding")
    if not isinstance(rendered, list) or any(not isinstance(part, str) for part in rendered):
        raise ValueError("invalid rendered health test")
    # Decode exactly one layer, rejecting an unmatched dollar. Do not use the
    # output of --no-interpolate or repeatedly decode until a comparison passes.
    if any("$" in part.replace("$$", "") for part in rendered):
        raise ValueError("rendered health test contains an unescaped dollar")
    if [part.replace("$$", "$") for part in rendered] != expected or engine != expected:
        raise ValueError("rendered/Engine health test differs from the approved application test")


def check_port_collisions(proposed, others, running_id):
    """Conservative TCP/UDP host-binding collision check against live owners."""
    host_config = single_inspect(proposed)["HostConfig"]
    if host_config.get("NetworkMode") == "host" or host_config.get("PublishAllPorts"):
        raise ValueError("host networking and automatic publication require separate review")
    target = host_config.get("PortBindings") or {}
    for bindings in target.values():
        for binding in bindings or []:
            if not str(binding.get("HostPort", "")).isdigit() or not 1 <= int(binding["HostPort"]) <= 65535:
                raise ValueError("an explicit single host port is required")
    for other in others:
        if (not isinstance(other, dict) or not isinstance(other.get("Id"), str)
                or not isinstance(other.get("State", {}).get("Running"), bool)
                or not isinstance(other.get("NetworkSettings"), dict)
                or "Ports" not in other["NetworkSettings"]):
            raise ValueError("incomplete supplied container inventory")
        if other["Id"] == running_id or not other["State"]["Running"]:
            continue
        for port, bindings in target.items():
            protocol = port.rsplit("/", 1)[-1]
            for binding in bindings or []:
                for occupied_port, occupied in (other.get("NetworkSettings", {}).get("Ports") or {}).items():
                    if occupied_port.rsplit("/", 1)[-1] != protocol:
                        continue
                    for owner in occupied or []:
                        if str(binding.get("HostPort")) != str(owner.get("HostPort")):
                            continue
                        left, right = binding.get("HostIp", ""), owner.get("HostIp", "")
                        wildcard = {"", "0.0.0.0", "::"}
                        try:
                            if left in wildcard or right in wildcard or ipaddress.ip_address(left) == ipaddress.ip_address(right):
                                raise ValueError("proposed host port is occupied by another running container")
                        except ValueError as exc:
                            if str(exc).startswith("proposed"):
                                raise
                            raise ValueError("unrecognized host binding address") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--running", required=True)
    parser.add_argument("--proposed", required=True)
    parser.add_argument("--other-containers", required=True)
    parser.add_argument("--reviewed-changes", required=True)
    parser.add_argument("--expected-changes-sha256", required=True)
    parser.add_argument("--health-evidence", required=True,
                        help="private JSON with encoded, rendered, engine and interpolated fields")
    args = parser.parse_args(argv)
    try:
        raw = Path(args.reviewed_changes).read_bytes()
        if not SHA256.fullmatch(args.expected_changes_sha256) or hashlib.sha256(raw).hexdigest() != args.expected_changes_sha256:
            raise ValueError("exact-change manifest digest mismatch")
        running, proposed = load_json(args.running), load_json(args.proposed)
        compare(running, proposed, json.loads(raw))
        evidence = load_json(args.health_evidence)
        if set(evidence) != {"encoded", "rendered", "engine", "interpolated"}:
            raise ValueError("invalid health evidence")
        verify_health(**evidence)
        if single_inspect(proposed)["Config"].get("Healthcheck", {}).get("Test") != evidence["engine"]:
            raise ValueError("health evidence does not match proposed Engine contract")
        others = load_json(args.other_containers)
        if not isinstance(others, list):
            raise ValueError("container inventory must be a list")
        check_port_collisions(proposed, others, single_inspect(running)["Id"])
    except (ValueError, KeyError, TypeError, OSError):
        print("Activation contract verification failed; inspect private evidence through the trusted route.", file=sys.stderr)
        return 1
    print("Offline supplied-file comparison passed. Activation authorization: false; use the actual chain/probe driver and owner runtime gates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
