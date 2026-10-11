#!/usr/bin/env python3
"""Stage private Unity art and package a verified compiled Web release only."""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile

REPOSITORY = "sock-lint/the-abby-project"
UNITY_VERSION = "6000.6.5f1"
LICENSED_SCENE = "Assets/AbbyCamp/Licensed/MemoryMeadow.unity"
PRIVATE_PATHS = (
    "Assets/ThirdParty/Meshtint", "Assets/ThirdParty/Meshtint.meta",
    "Assets/AbbyCamp/Licensed", "Assets/AbbyCamp/Licensed.meta",
)
ART_SUFFIXES = {
    ".fbx", ".png", ".psd", ".jpg", ".jpeg", ".tga", ".mat", ".prefab",
    ".anim", ".controller", ".avatar", ".asset", ".unity", ".meta", ".json", ".txt",
}
STATIC_SUFFIXES = {".css", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ttf", ".otf", ".woff", ".woff2", ".txt", ".ico"}
SHA_PATTERN = re.compile(r"[a-f0-9]{40}\Z")
RUNTIME_PATTERN = re.compile(r"Build/[a-f0-9]{32}\.(data|wasm|framework\.js|loader\.js)\Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or "\\" in value or path.is_absolute() or ".." in path.parts
            or str(path) != value or any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in path.parts)):
        raise ValueError("Release contains an unsafe relative path.")
    return value


def regular_files(root: Path) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Expected an ordinary directory, not a link.")
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError("Links and special files are not allowed in release inputs.")
        if path.is_file():
            files.append(path)
    return files


def validate_source(repository: Path, source_commit: str) -> None:
    if not SHA_PATTERN.fullmatch(source_commit):
        raise ValueError("Source commit must be a full lowercase 40-character Git SHA.")
    head = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    if head != source_commit:
        raise ValueError("The requested source commit does not match this checkout.")
    origin = subprocess.check_output(["git", "-C", str(repository), "remote", "get-url", "origin"], text=True).strip()
    if origin.removesuffix(".git") not in {f"https://github.com/{REPOSITORY}", f"git@github.com:{REPOSITORY}"}:
        raise ValueError("The release checkout is not the expected GitHub repository.")
    status = subprocess.check_output(
        ["git", "-C", str(repository), "status", "--porcelain", "--untracked-files=normal"], text=True,
    )
    if status:
        raise ValueError("Release source must be a clean checkout; ignored private inputs are permitted.")
    version = repository / "unity/AbbyCamp/ProjectSettings/ProjectVersion.txt"
    if f"m_EditorVersion: {UNITY_VERSION}" not in version.read_text(encoding="utf-8").splitlines():
        raise ValueError("The source checkout does not pin the supported release editor.")


def reject_link_components(root: Path, path: Path) -> None:
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("Private art path components must not be links.")


def private_assets_digest(root: Path) -> str:
    records = {}
    for relative in PRIVATE_PATHS:
        source = root / relative
        reject_link_components(root, source)
        if source.is_symlink() or not source.exists():
            raise ValueError("A required private art tree or its Unity metadata is missing.")
        files = regular_files(source) if source.is_dir() else [source]
        if not files:
            raise ValueError("A required private art tree is empty.")
        for path in files:
            if path.suffix.lower() not in ART_SUFFIXES or not path.is_file():
                raise ValueError("Private staging accepts prepared art data only, never executable code.")
            if path.stat().st_size > 512 * 1024 * 1024:
                raise ValueError("A private art input exceeds the per-file bound.")
            if path.suffix != ".meta" and not Path(str(path) + ".meta").is_file():
                raise ValueError("Every prepared Unity art asset must retain its metadata GUID.")
            name = path.relative_to(root).as_posix()
            records[name] = {"size": path.stat().st_size, "sha256": sha256(path)}
    return hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def stage_private_assets(repository: Path, private_root: Path) -> str:
    """Copy only the two prepared art trees, preserving every .meta and scene."""
    repository = repository.resolve()
    if private_root.is_symlink():
        raise ValueError("Private input root must not be a link.")
    private_root = private_root.resolve(strict=True)
    if private_root == repository or private_root.is_relative_to(repository):
        raise ValueError("Private art must be configured outside the source checkout.")
    project = repository / "unity/AbbyCamp"
    if not (private_root / LICENSED_SCENE).is_file():
        raise ValueError("Prepared licensed MemoryMeadow scene is required; fallback art is not a release.")
    digest = private_assets_digest(private_root)
    staged = []
    for relative in PRIVATE_PATHS:
        source = private_root / relative
        target = project / relative
        reject_link_components(private_root, source)
        reject_link_components(repository, target)
        if source.is_symlink() or not source.exists():
            raise ValueError("A required private art tree or its Unity metadata is missing.")
        if target.exists() or target.is_symlink():
            raise ValueError("Private staging destinations must be fresh; refusing to overwrite local art.")
        staged.append((source, target))
    # Validate the complete input before writing anything. No generation or fallback.
    for source, target in staged:
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copyfile(source, target)
    if private_assets_digest(project) != digest:
        raise ValueError("Private art changed during staging.")
    return digest


class ResourceReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "link" and attributes.get("href"):
            self.references.append(attributes["href"])
        elif tag in {"script", "img", "source"} and attributes.get("src"):
            self.references.append(attributes["src"])


def validate_export(export: Path) -> tuple[list[Path], dict[str, str]]:
    files = regular_files(export)
    for path in files:
        relative = safe_relative(path.relative_to(export).as_posix())
        if relative == "index.html" or RUNTIME_PATTERN.fullmatch(relative):
            pass
        elif relative.startswith("TemplateData/") and path.suffix.lower() in STATIC_SUFFIXES:
            pass
        else:
            raise ValueError("Export includes a source asset, stale build, or unsupported static file.")
        if path.stat().st_size == 0:
            raise ValueError("Empty release files are not allowed.")
    index = export / "index.html"
    if not index.is_file():
        raise ValueError("The export is missing index.html.")
    html = index.read_text(encoding="utf-8")
    if "{{{" in html or "unity-canvas" not in html:
        raise ValueError("Expected a compiled Unity Web template.")
    references = {}
    for key, pattern, extension in (
        ("data", r"\bdataUrl\s*:\s*['\"]([^'\"]+)['\"]", ".data"),
        ("framework", r"\bframeworkUrl\s*:\s*['\"]([^'\"]+)['\"]", ".framework.js"),
        ("wasm", r"\bcodeUrl\s*:\s*['\"]([^'\"]+)['\"]", ".wasm"),
        ("loader", r"\bloader\.src\s*=\s*['\"]([^'\"]+)['\"]", ".loader.js"),
    ):
        matches = re.findall(pattern, html)
        if len(matches) != 1 or not RUNTIME_PATTERN.fullmatch(matches[0]) or not matches[0].endswith(extension):
            raise ValueError("Unity HTML must reference exactly one hashed file for each runtime component.")
        references[key] = matches[0]
    actual_runtime = {path.relative_to(export).as_posix() for path in files if path.parent == export / "Build"}
    if actual_runtime != set(references.values()):
        raise ValueError("Runtime references do not match the export; a file is missing or stale.")
    resources = ResourceReferences()
    resources.feed(html)
    for relative in resources.references:
        safe_relative(relative)
        if not (export / relative).is_file():
            raise ValueError("A template resource does not exist in the export.")
    # CSS cannot point at an absent font/image or external source.
    for path in files:
        if path.suffix == ".css":
            for value in re.findall(r"url\(\s*['\"]?([^)'\"\s]+)['\"]?\s*\)", path.read_text(encoding="utf-8")):
                safe_relative(value)
                if not (path.parent / value).is_file():
                    raise ValueError("A stylesheet resource is absent from the export.")
    return files, references


def package_release(repository: Path, export: Path, output: Path, source_commit: str,
                    run_id: str, run_attempt: str, licensed_assets_digest: str) -> dict:
    validate_source(repository, source_commit)
    if not re.fullmatch(r"[1-9][0-9]*", run_id) or not re.fullmatch(r"[1-9][0-9]*", run_attempt):
        raise ValueError("Run ID and attempt must be positive decimal strings.")
    if not re.fullmatch(r"[a-f0-9]{64}", licensed_assets_digest):
        raise ValueError("A verified private art digest is required.")
    scene = repository / "unity/AbbyCamp" / LICENSED_SCENE
    if scene.is_symlink() or not scene.is_file():
        raise ValueError("The compiled release must use the preserved licensed scene.")
    if private_assets_digest(repository / "unity/AbbyCamp") != licensed_assets_digest:
        raise ValueError("Prepared private art changed after staging; its release digest does not match.")
    files, references = validate_export(export)
    output = output.resolve()
    if (output == export.resolve() or output.is_relative_to(export.resolve())
            or export.resolve().is_relative_to(output)):
        raise ValueError("Package output must be outside the Web export.")
    output.mkdir(parents=True, exist_ok=True)
    manifest_path, archive_path = output / "release.json", output / "web.tar.gz"
    if manifest_path.exists() or archive_path.exists():
        raise ValueError("Release outputs already exist; use a fresh release directory.")
    manifest = {
        "schema_version": 1, "repository": REPOSITORY, "source_commit": source_commit,
        "release_id": f"{source_commit}-{run_id}-{run_attempt}",
        "run_id": run_id, "run_attempt": run_attempt, "unity_version": UNITY_VERSION,
        "licensed_assets_digest": licensed_assets_digest,
        "scene": {"path": LICENSED_SCENE, "sha256": sha256(scene)},
        "runtime_files": references,
        "files": {path.relative_to(export).as_posix(): {"size": path.stat().st_size, "sha256": sha256(path)} for path in files},
    }
    encoded = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    # Build from explicit regular-file members; never archive the source checkout.
    with tarfile.open(archive_path, "w:gz", dereference=False) as archive:
        for path in files:
            relative = path.relative_to(export).as_posix()
            record = manifest["files"][relative]
            with path.open("rb") as source:
                member = tarfile.TarInfo("web/" + relative)
                member.size, member.mode = record["size"], 0o644
                archive.addfile(member, source)
            if sha256(path) != record["sha256"]:
                raise ValueError("The Web export changed while it was packaged.")
        member = tarfile.TarInfo("web/release.json")
        member.size, member.mode = len(encoded), 0o644
        archive.addfile(member, io.BytesIO(encoded))
    # Check the archived bytes, not just source files that could change mid-read.
    with tarfile.open(archive_path, "r:gz") as archive:
        for relative, record in manifest["files"].items():
            digest = hashlib.sha256()
            with archive.extractfile("web/" + relative) as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != record["sha256"]:
                raise ValueError("The archived runtime bytes do not match the release manifest.")
    validate_source(repository, source_commit)
    manifest_path.write_bytes(encoded)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage-assets")
    stage.add_argument("--repository", type=Path, required=True)
    stage.add_argument("--private-root", type=Path, required=True)
    package = commands.add_parser("package")
    for name in ("repository", "export", "output"):
        package.add_argument("--" + name, type=Path, required=True)
    for name in ("source-commit", "run-id", "run-attempt", "licensed-assets-digest"):
        package.add_argument("--" + name, required=True)
    args = parser.parse_args()
    try:
        if args.command == "stage-assets":
            print(stage_private_assets(args.repository, args.private_root))
        else:
            manifest = package_release(args.repository, args.export, args.output, args.source_commit,
                                       args.run_id, args.run_attempt, args.licensed_assets_digest)
            print(json.dumps({"release_id": manifest["release_id"], "archive_sha256": sha256(args.output / "web.tar.gz")}, sort_keys=True))
    except (ValueError, OSError, subprocess.CalledProcessError):
        parser.exit(1, "Unity release input validation or packaging failed; no deployment was performed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
