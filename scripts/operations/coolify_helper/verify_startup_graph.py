#!/usr/bin/env python3
"""Compile the candidate's actual s6 graph without running its entrypoint.

No networking, host mounts, environment files, Docker socket or service startup
is permitted. Only a disposable container's bounded /tmp tmpfs is writable.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess


REQUIRED_DEPENDENCIES = {
    "nginx": {"php-fpm", "init-script"},
    "php-fpm": {"init-script"},
    "horizon": {"init-script"},
    "scheduler-worker": {"init-script"},
    "init-script": {"init-seeder"},
    "init-seeder": {"db-migration"},
}

COMPILE_AND_QUERY = """set -eu
export PATH=/command:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
/command/s6-rc-compile -v0 /tmp/coolify-graph \\
  /etc/s6-overlay/s6-rc.d \\
  /package/admin/s6-overlay/etc/s6-rc/sources
/command/s6-rc-db -c /tmp/coolify-graph check
for service in nginx php-fpm horizon scheduler-worker init-script init-seeder; do
  printf '__S6_DEPS__ %s\\n' "$service"
  /command/s6-rc-db -c /tmp/coolify-graph dependencies "$service"
done
"""


def parse_and_validate_dependencies(output: str) -> dict[str, list[str]]:
    """Reject graph drift, including dependencies.d hiding nginx's flat file."""
    dependencies: dict[str, list[str]] = {}
    service = None
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("__S6_DEPS__ "):
            service = line.removeprefix("__S6_DEPS__ ")
            if service not in REQUIRED_DEPENDENCIES or service in dependencies:
                raise ValueError("Unexpected or repeated service in compiled graph")
            dependencies[service] = []
        elif service is not None and re.fullmatch(r"[a-zA-Z0-9_.:-]+", line):
            dependencies[service].append(line)
        else:
            raise ValueError("Unexpected compiled graph output")
    for service, required in REQUIRED_DEPENDENCIES.items():
        missing = required - set(dependencies.get(service, []))
        if missing:
            raise ValueError(
                f"Compiled {service} dependencies missing: {', '.join(sorted(missing))}"
            )
    return dependencies


def verify(image: str) -> dict[str, object]:
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise ValueError("Supply the already-built immutable local image ID")
    command = [
        "docker", "run", "--rm", "--pull=never", "--network=none",
        "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=64", "--memory=128m", "--cpus=1", "--user=www-data",
        "--tmpfs=/tmp:rw,nosuid,nodev,size=32m", "--entrypoint=/bin/sh",
        "-i", image, "-s",
    ]
    result = subprocess.run(
        command, input=COMPILE_AND_QUERY, capture_output=True, text=True,
        timeout=90, check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Isolated s6 compilation/check failed (exit {result.returncode}); "
            "no service entrypoint was run"
        )
    return {
        "schema_version": 1,
        "image_id": image,
        "network": "none",
        "root_filesystem": "read-only",
        "runtime_user": "www-data",
        "host_mounts": [],
        "service_entrypoint_executed": False,
        "graph_compiled_and_checked": True,
        "direct_dependencies": parse_and_validate_dependencies(result.stdout),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_id", help="Already-built immutable sha256 image ID")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.image_id), indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Startup graph verification failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
