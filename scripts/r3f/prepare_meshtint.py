#!/usr/bin/env python
"""Prepare a private, bounded R3F export from the recorded owned Meshtint art.

Requires Blender 4.1+ and Pillow. Reads selected FBX/PSD sources without
modifying them. Purchased sources and runtime exports must remain ignored;
this tool does not authorize public redistribution or upload anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
LICENSE_URL = "https://www.meshtint.com/pages/terms-of-use-license"
CREATURES = {
    "chick": {
        "form": "Chick", "idle": "Idle", "height": 1.8,
        "interactions": {"play": "Jump Forward In Place", "left": "Turn Left", "right": "Turn Right"},
    },
    "bird": {
        "form": "Bird", "idle": "Fly Idle", "height": 2.0,
        "interactions": {"play": "Fly Forward In Place", "left": "Turn Left", "right": "Turn Right"},
    },
}
FOREST_MODELS = (
    "FBX/FBX 1.1/Ground 01 Soft Edge.FBX", "FBX/Tree 02.FBX",
    "FBX/Rock 01.FBX", "FBX/Mushroom 01.FBX", "FBX/Ancient Pillar 01.FBX",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def glb_document(path: Path) -> dict:
    data = path.read_bytes()
    magic, version, size = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or size != len(data):
        raise ValueError("Invalid GLB header")
    chunk_size, kind = struct.unpack_from("<II", data, 12)
    if kind != 0x4E4F534A or chunk_size > len(data) - 20:
        raise ValueError("Missing GLB JSON chunk")
    document = json.loads(data[20:20 + chunk_size])
    if any("uri" in entry for entry in document.get("buffers", []) + document.get("images", [])):
        raise ValueError("Runtime export contains an external file reference")
    if not document.get("meshes") or not document.get("images"):
        raise ValueError("Runtime export is missing textured geometry")
    return document


def verify_export(path: Path, required_clips: list[str]) -> dict:
    document = glb_document(path)
    animations = document.get("animations", [])
    names = [animation.get("name") for animation in animations]
    if sorted(names) != sorted(required_clips):
        raise ValueError(f"Exported clips differ from reviewed clips: {names}")
    for animation in animations:
        if not animation.get("channels") or not animation.get("samplers"):
            raise ValueError("Empty animation clip")
        for sampler in animation["samplers"]:
            time = document["accessors"][sampler["input"]]
            if time["count"] < 2 or time.get("max", [0])[0] <= time.get("min", [0])[0]:
                raise ValueError("Animation has no positive playback duration")
    if required_clips and not document.get("skins"):
        raise ValueError("Creature has no exported skin")
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            if primitive.get("mode", 4) != 4 or "TEXCOORD_0" not in primitive["attributes"]:
                raise ValueError("Expected triangle geometry with supplied UVs")
            if required_clips and not {"JOINTS_0", "WEIGHTS_0"}.issubset(primitive["attributes"]):
                raise ValueError("Creature mesh has lost skinning")
    return {
        "sha256": sha256(path), "bytes": path.stat().st_size,
        "mesh_count": len(document["meshes"]), "skin_count": len(document.get("skins", [])),
        "clips": names, "embedded_images": len(document["images"]),
    }


def find_blender(value: str | None) -> Path:
    if value:
        candidate = Path(value).resolve()
    else:
        installed = shutil.which("blender")
        candidates = sorted(Path("C:/Program Files/Blender Foundation").glob("Blender */blender.exe"))
        candidate = Path(installed) if installed else candidates[-1] if candidates else Path("blender")
    if not candidate.is_file():
        raise FileNotFoundError("Blender executable not found; pass --blender")
    return candidate


def ensure_private_output(output: Path, source: Path) -> None:
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Output must not overlap purchased sources")
    if output.is_relative_to(ROOT):
        probe = subprocess.run(
            ["git", "check-ignore", "--quiet", str(output / "manifest.json")],
            cwd=ROOT, check=False,
        )
        if probe.returncode:
            raise ValueError("In-repository output must be ignored before conversion")


def prepare(source: Path, output: Path, blender: Path) -> dict:
    from PIL import Image, UnidentifiedImageError

    forest = "Forest Ruins Pack Cute Series"
    selected: dict[str, Path] = {}
    for entry in CREATURES.values():
        folder = f"{entry['form']} Cute Series"
        for clip in (entry["idle"], *entry["interactions"].values()):
            relative = f"{folder}/FBX/{entry['form']}@{clip}.FBX"
            selected[relative] = source / relative
        relative = f"{folder}/Textures/{entry['form']}.psd"
        selected[relative] = source / relative
    for relative in FOREST_MODELS:
        selected[f"{forest}/{relative}"] = source / forest / relative
    for name in ("Forest Ruins", "Tree 02 Leaves"):
        relative = f"{forest}/Textures/{name}.psd"
        selected[relative] = source / relative
    leaf_material = f"{forest}/Materials/Tree 02 Leaves Blue.mat"
    selected[leaf_material] = source / leaf_material
    if any(not path.is_file() for path in selected.values()):
        raise FileNotFoundError("A reviewed creature, clip, woodland model or PSD source is missing")
    before = {relative: sha256(path) for relative, path in selected.items()}
    scratch_root = ROOT / "scripts/r3f/private"
    scratch_root.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="conversion-", dir=scratch_root) as temporary:
        scratch = Path(temporary)
        textures = {}
        for relative, path in selected.items():
            if path.suffix.lower() != ".psd":
                continue
            destination = scratch / (path.stem + ".png")
            try:
                image = Image.open(path)
            except UnidentifiedImageError:
                # The supplied foliage PSD is 16-bit; preserve its merged preview.
                from psd_tools import PSDImage
                image = PSDImage.open(path).topil()
                if image is None:
                    raise ValueError("PSD has no readable merged preview")
            with image:
                runtime = image.convert("RGBA")
                runtime.thumbnail((512, 512), Image.Resampling.LANCZOS)
                runtime.save(destination)
            textures[path.stem] = str(destination)
        color_match = re.search(r"- _(BaseColor|Color): \{r: ([\d.eE+-]+), g: ([\d.eE+-]+), b: ([\d.eE+-]+), a: ([\d.eE+-]+)\}", selected[leaf_material].read_text(encoding="utf-8"))
        if not color_match:
            raise ValueError("Supplied foliage material color is missing")
        material_colors = {"Tree 02 Leaves": [float(value) for value in color_match.groups()[1:]]}
        config = {"source": str(source), "output": str(output), "textures": textures, "creatures": CREATURES, "material_colors": material_colors}
        config_path = scratch / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        process = subprocess.run([
            str(blender), "--background", "--factory-startup", "--python-exit-code", "1",
            "--python", str(ROOT / "scripts/r3f/blender_meshtint.py"), "--", str(config_path),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        # Blender importer output may contain private filenames. Keep its full log private.
        (scratch_root / "conversion.log").write_text(process.stdout + process.stderr, encoding="utf-8")
        if process.returncode:
            raise RuntimeError("Blender conversion failed; inspect scripts/r3f/private/conversion.log")
    after = {relative: sha256(path) for relative, path in selected.items()}
    if before != after:
        raise RuntimeError("Original purchased inputs changed during conversion")
    models = {}
    for key, entry in CREATURES.items():
        filename = key + ".glb"
        metadata = verify_export(output / filename, [entry["idle"]])
        models[key] = {
            "file": filename, "idle_clip": entry["idle"], "movement_clip": None,
            "scale": 1, "rotation_y": 0, **metadata,
        }
        models[key]["interaction_clips"] = {
            interaction: {
                "file": f"{key}-{interaction}.glb", "clip": clip,
                "return_motion": "reverse" if interaction in ("left", "right") else "idle",
                **verify_export(output / f"{key}-{interaction}.glb", [clip]),
            }
            for interaction, clip in entry["interactions"].items()
        }
    models["woodland"] = {
        "file": "woodland.glb", "scale": 1, "rotation_y": 0,
        **verify_export(output / "woodland.glb", []),
    }
    woodland = glb_document(output / "woodland.glb")
    foliage = [item for item in woodland.get("materials", []) if item.get("name") == "Tree 02 Leaves Runtime"]
    if len(foliage) != 1 or foliage[0].get("alphaMode") != "MASK" or not foliage[0].get("doubleSided"):
        raise ValueError("Supplied foliage atlas/alpha cutout was not preserved")
    manifest = {
        "schema_version": 1, "delivery_review": "private_evaluation",
        "license_url": LICENSE_URL,
        "bindings": [{"species_slug": "chick", "species_sprite_key": "cute-chick", "potion_slug": "base", "pet": "chick", "evolved": "bird", "mount": "bird"}],
        "models": models,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    report = {
        "schema_version": 1, "input_sha256": before, "originals_unchanged": True,
        "exporter_sha256": sha256(ROOT / "scripts/r3f/blender_meshtint.py"),
        "manifest": manifest,
        "skinning_validation": json.loads((output / "skinning-validation.json").read_text(encoding="utf-8")),
    }
    (scratch_root / "conversion-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output / "skinning-validation.json").unlink()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Privately staged Assets/ThirdParty/Meshtint directory")
    parser.add_argument("--output", type=Path, default=ROOT / "frontend/src/companion/licensed")
    parser.add_argument("--blender", help="Blender executable")
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    ensure_private_output(output, source)
    manifest = prepare(source, output, find_blender(args.blender))
    print("Prepared private idle, interaction and woodland GLBs; original inputs are unchanged.")  # noqa: T201 — CLI status
    print("Verified embedded textures, skinning and exact supplied clip names; phone acceptance and delivery review remain open.")  # noqa: T201 — CLI status
    print(json.dumps({key: {"bytes": item["bytes"], "clips": item["clips"]} for key, item in manifest["models"].items()}))  # noqa: T201 — CLI evidence summary
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
