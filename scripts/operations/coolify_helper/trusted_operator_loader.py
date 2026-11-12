"""Load captured operator source after a trusted isolated inline bootstrap.

This file is itself externally SHA-pinned before execution with python -I -S.
It never changes sys.path, imports checkout bytecode, builds images, or invokes
services. The selected reviewed entry owns any later explicitly approved action.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from types import ModuleType


DRIVER_FILES = ("verify_activation_contract.py", "compose_contract_projection.py", "capture_activation_contract.py")
STANDALONE_FILES = {"verify_reviewed_source.py", "verify_startup_graph.py"}
OPERATOR_FILES = {*DRIVER_FILES, *STANDALONE_FILES, "trusted_operator_loader.py"}


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate binding key")
        value[key] = item
    return value


def captured_regular_file(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("canonical regular source path required")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("regular source file required")
        payload = stream.read(16 * 1024 * 1024 + 1)
    if len(payload) > 16 * 1024 * 1024:
        raise ValueError("source or binding too large")
    return payload


def matched(payload, expected):
    if type(expected) is not str or len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        raise ValueError("independent source digest required")
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError("captured source digest mismatch")


def operator_binding(payload, expected_manifest_sha, entry=None, expected_entry_sha=None):
    matched(payload, expected_manifest_sha)
    manifest = json.loads(payload, object_pairs_hook=unique_object)
    tools = manifest.get("operator_tools") if type(manifest) is dict else None
    if type(tools) is not dict or set(tools) != OPERATOR_FILES:
        raise ValueError("same approved manifest must bind the closed operator tool set")
    for value in tools.values():
        if type(value) is not str or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError("invalid operator tool digest")
    if tools["trusted_operator_loader.py"] != globals().get("_TRUSTED_OPERATOR_ENTRY_SHA256"):
        raise ValueError("executed loader pin differs from the approved manifest")
    if entry is not None and tools.get(entry) != expected_entry_sha:
        raise ValueError("entry pin differs from the same approved manifest")
    return tools


def load_driver_buffers(buffers, expected, filenames):
    """Verify ALL closed-set buffers before ANY source executes."""
    if set(buffers) != set(DRIVER_FILES) or set(expected) != set(DRIVER_FILES) or set(filenames) != set(DRIVER_FILES):
        raise ValueError("unknown or missing operator module")
    for name in DRIVER_FILES:
        if type(buffers[name]) is not bytes:
            raise ValueError("captured source bytes required")
        matched(buffers[name], expected[name])
    modules = {}
    for name in DRIVER_FILES:
        key = name[:-3]
        if key in sys.modules:
            raise ValueError("operator module was imported before verified capture")
        module = ModuleType(key)
        module.__file__ = str(filenames[name])
        module.__dict__["_TRUSTED_TOOL_SHA256"] = dict(expected)
        module.__dict__["_TRUSTED_OPERATOR_ENTRY_SHA256"] = expected[name]
        modules[key] = module
    # Sibling imports resolve only these already captured, verified modules.
    sys.modules.update(modules)
    try:
        for name in DRIVER_FILES:
            module = modules[name[:-3]]
            exec(compile(buffers[name], str(filenames[name]), "exec"), module.__dict__)
    except BaseException:
        for key, module in modules.items():
            if sys.modules.get(key) is module:
                del sys.modules[key]
        raise
    return modules["capture_activation_contract"]


def standalone(tool_dir, entry, expected_sha, arguments, manifest_path, manifest_sha):
    if entry not in STANDALONE_FILES:
        raise ValueError("unknown standalone entry")
    operator_binding(captured_regular_file(manifest_path), manifest_sha, entry, expected_sha)
    filename = Path(tool_dir) / entry
    source = captured_regular_file(filename)
    matched(source, expected_sha)
    namespace = {"__name__": "__main__", "__file__": str(filename),
                 "_TRUSTED_OPERATOR_ENTRY_SHA256": expected_sha,
                 "_TRUSTED_OPERATOR_LOADER_SHA256": globals()["_TRUSTED_OPERATOR_ENTRY_SHA256"]}
    previous = sys.argv
    try:
        sys.argv = [str(filename), *arguments]
        exec(compile(source, str(filename), "exec"), namespace)
    finally:
        sys.argv = previous
    return 0


def driver(tool_dir, plan_path, plan_sha, operator_state_dir, manifest_path, manifest_sha, changes_path=None, changes_sha=None):
    raw_plan = captured_regular_file(plan_path)
    matched(raw_plan, plan_sha)
    plan = json.loads(raw_plan, object_pairs_hook=unique_object)
    expected = plan.get("tool_inputs") if type(plan) is dict else None
    if type(expected) is not dict or set(expected) != set(DRIVER_FILES):
        raise ValueError("closed operator source binding required")
    approved = operator_binding(captured_regular_file(manifest_path), manifest_sha)
    if expected != {name: approved[name] for name in DRIVER_FILES}:
        raise ValueError("driver plan tools differ from the same approved source manifest")
    filenames = {name: Path(tool_dir) / name for name in DRIVER_FILES}
    # Capture every entry/sibling and verify every digest before any imports.
    buffers = {name: captured_regular_file(path) for name, path in filenames.items()}
    entry = load_driver_buffers(buffers, expected, filenames)
    raw_changes = captured_regular_file(changes_path) if changes_path else None
    if raw_changes is not None:
        matched(raw_changes, changes_sha)
    try:
        result = entry.observe(raw_plan, expected_plan_sha256=plan_sha, operator_state_dir=operator_state_dir,
                               reviewed_changes=raw_changes, expected_changes_sha256=changes_sha)
    except entry.OperationFailure as error:
        print(json.dumps({"schema_version": 1, "error": "operator_operation_failed", **error.status}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv=None):
    if not sys.flags.isolated or not sys.flags.no_site or not globals().get("_TRUSTED_OPERATOR_ENTRY_SHA256"):
        raise ValueError("externally pinned isolated inline bootstrap required")
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    single = commands.add_parser("standalone", allow_abbrev=False)
    single.add_argument("--tool-dir", required=True)
    single.add_argument("--entry", required=True, choices=sorted(STANDALONE_FILES))
    single.add_argument("--expected-entry-sha256", required=True)
    single.add_argument("--operator-manifest", required=True)
    single.add_argument("--expected-operator-manifest-sha256", required=True)
    single.add_argument("arguments", nargs=argparse.REMAINDER)
    capture = commands.add_parser("driver", allow_abbrev=False)
    capture.add_argument("--tool-dir", required=True)
    capture.add_argument("--plan", required=True)
    capture.add_argument("--expected-plan-sha256", required=True)
    capture.add_argument("--operator-state-dir", required=True)
    capture.add_argument("--operator-manifest", required=True)
    capture.add_argument("--expected-operator-manifest-sha256", required=True)
    capture.add_argument("--reviewed-changes")
    capture.add_argument("--expected-changes-sha256")
    args = parser.parse_args(argv)
    if args.command == "standalone":
        arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        return standalone(args.tool_dir, args.entry, args.expected_entry_sha256, arguments,
                          args.operator_manifest, args.expected_operator_manifest_sha256)
    return driver(args.tool_dir, args.plan, args.expected_plan_sha256, args.operator_state_dir,
                  args.operator_manifest, args.expected_operator_manifest_sha256,
                  args.reviewed_changes, args.expected_changes_sha256)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError):
        print("Verified operator loading failed; no authority inferred from checkout files.", file=sys.stderr)
        sys.exit(1)
