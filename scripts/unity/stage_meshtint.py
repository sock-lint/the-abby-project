#!/usr/bin/env python
"""Stage purchased Cute Series packs locally without publishing their sources.

Unity package GUIDs are retained while paths move below the ignored Meshtint
folder. Only art data is imported; publisher demo scenes and scripts are skipped.
The public prototype stays usable without these files.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
UNITY = ROOT / "unity/AbbyCamp"
SOURCE = UNITY / "Assets/ThirdParty/Meshtint"
LICENSED = UNITY / "Assets/AbbyCamp/Licensed"
PACKS = (
    "Chick Fledgling Bird Evolution Pack Cute series.zip",
    "Forest Ruins Pack Cute Series 1.2.zip",
    "Icons For Monsters Ultimate Pack 01 Cute Series v2.zip",
    "Female Archer Modular Pack 01 Cute Series.zip",
)
ART_TYPES = {".fbx", ".png", ".psd", ".jpg", ".jpeg", ".tga", ".mat", ".prefab", ".anim", ".controller", ".avatar"}


def safe_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts or ":" in value:
        raise ValueError(f"Unsafe archive path: {value}")
    return path


def stage_package(data: bytes) -> int:
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = {member.name.removeprefix("./"): member for member in archive.getmembers() if member.isfile()}
        for name, member in members.items():
            if not name.endswith("/pathname"):
                continue
            pathname = archive.extractfile(member).read().decode("utf-8").strip()
            path = safe_path(pathname)
            if path.parts[0] != "Assets":
                raise ValueError(f"Package asset outside Assets: {pathname}")
            if path.suffix.lower() not in ART_TYPES or any("demo" in part.lower() for part in path.parts):
                continue
            target = SOURCE.joinpath(*path.parts[1:])
            prefix = name.removesuffix("pathname")
            for part, output in (("asset", target), ("asset.meta", Path(str(target) + ".meta"))):
                source = members.get(prefix + part)
                if source is None:
                    raise ValueError(f"Missing {part}: {pathname}")
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(archive.extractfile(source).read())
            count += 1
    return count


def stage_archive(data: bytes, depth: int = 0) -> int:
    if depth > 3:
        raise ValueError("Unexpectedly deep nested ZIP")
    count = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for item in archive.infolist():
            path = safe_path(item.filename)
            if item.is_dir():
                continue
            if item.file_size > 400_000_000:
                raise ValueError(f"Unexpectedly large asset: {item.filename}")
            if path.suffix.lower() == ".zip":
                count += stage_archive(archive.read(item), depth + 1)
            elif path.suffix.lower() == ".unitypackage":
                count += stage_package(archive.read(item))
            elif "transparent bg" in [part.lower() for part in path.parts] and path.name in {"Bird01.png", "Bird02.png", "Bird03.png"}:
                target = LICENSED / "Art" / {"Bird01.png": "chick.png", "Bird02.png": "fledgling.png", "Bird03.png": "bird.png"}[path.name]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    args = parser.parse_args()
    report = {"license_url": "https://www.meshtint.com/pages/terms-of-use-license", "packs": []}
    missing = []
    candidates = list(args.downloads.glob("*.zip"))
    for name in PACKS:
        archive = args.downloads / name
        if not archive.is_file() and name.startswith("Female Archer"):
            archive = next((p for p in candidates if "female archer" in p.name.lower() and "cute" in p.name.lower()), archive)
        if not archive.is_file():
            missing.append(name)
            continue
        data = archive.read_bytes()
        count = stage_archive(data)
        report["packs"].append({"filename": archive.name, "sha256": hashlib.sha256(data).hexdigest(), "imported_assets": count})
        print(f"Staged {archive.name}: {count} art assets")
    if any(name in missing for name in PACKS[:3]):
        raise FileNotFoundError("The bird, forest and icon archives are required.")
    profile = json.loads((ROOT / "shared/storybook/presentation.json").read_text(encoding="utf-8"))
    profile["companion"].update(label="Your chick", art_key="chick", temporary=False, portrait="chick.png", happy_portrait="chick.png", blink_portrait="chick.png")
    for target in (ROOT / "shared/storybook/licensed", ROOT / "frontend/src/storybook/licensed"):
        target.mkdir(parents=True, exist_ok=True)
        (target / "presentation.json").write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        for filename in ("chick.png", "fledgling.png", "bird.png"):
            shutil.copyfile(LICENSED / "Art" / filename, target / filename)
    LICENSED.mkdir(parents=True, exist_ok=True)
    (LICENSED / "import-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name in missing:
        print(f"Not found (can add later): {name}")
    print("Licensed files staged locally. Next run AbbyCamp.Editor.MeshtintSetup.Prepare in Unity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
