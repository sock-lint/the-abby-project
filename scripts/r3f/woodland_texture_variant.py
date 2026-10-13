"""Private Blender4.1 texture trial; no original, repository or network writes.

Run Blender --background --factory-startup --python-exit-code 1 --python this.py
-- --baseline /private/baseline/woodland.glb --output /private/trials/new-name
--verify-script /trusted/scripts/r3f/verify_exports_blender.py
Outputs a bounded texture-only candidate and a private structural comparison.
The trusted browser runner produces production-component preview evidence.
No phone/WebGL acceptance or public-delivery permission is inferred.
"""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct
import sys

import bpy
from mathutils import Vector

VERIFY_HASH = "07fc4e042a8872b123bd84fc8dcaa4b30f10a1dc88df2998931f94121706e5c2"
MAX_FILE = 64 * 1024 * 1024
SEED = 23
TEXTURE_DIMENSION = 256


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def input_bytes(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_FILE, "Input must be bounded regular file")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        opened = os.fstat(stream.fileno())
        require((opened.st_dev, opened.st_ino, opened.st_size) == (info.st_dev, info.st_ino, info.st_size), "Input identity changed")
        data = stream.read(MAX_FILE + 1)
    require(len(data) == info.st_size, "Input size changed")
    return data


def glb(path):
    data = input_bytes(path)
    require(len(data) >= 28, "Truncated GLB")
    magic, version, size = struct.unpack_from("<4sII", data)
    require(magic == b"glTF" and version == 2 and size == len(data), "Invalid GLB header")
    chunks = {}
    offset = 12
    while offset < len(data):
        require(offset + 8 <= len(data), "Truncated GLB chunk")
        length, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        require(kind not in chunks and offset + length <= len(data) and length % 4 == 0, "Invalid GLB chunk")
        chunks[kind] = data[offset:offset + length]
        offset += length
    require(set(chunks) == {0x4E4F534A, 0x004E4942}, "Expected JSON and embedded binary")
    doc = json.loads(chunks[0x4E4F534A])
    binary = chunks[0x004E4942]
    require(doc.get("asset", {}).get("version") == "2.0" and len(doc.get("buffers", [])) == 1, "Invalid static glTF")
    require(not doc.get("animations") and not doc.get("skins") and not doc.get("cameras"), "Static woodland only")
    require("KHR_lights_punctual" not in doc.get("extensions", {}), "No imported lights")
    require(not doc.get("extensionsRequired"), "Unsupported required extension")
    require(not any("uri" in item for item in doc.get("buffers", []) + doc.get("images", [])), "External reference refused")
    require(doc.get("meshes") and 0 < len(doc.get("images", [])) <= 32, "Missing textured geometry")
    images = []
    for image in doc["images"]:
        require(image.get("mimeType") == "image/png" and "bufferView" in image, "Expected embedded PNG")
        view = doc["bufferViews"][image["bufferView"]]
        start, length = view.get("byteOffset", 0), view["byteLength"]
        require(view.get("buffer", 0) == 0 and start >= 0 and length >= 24 and start + length <= len(binary), "Image bounds invalid")
        payload = binary[start:start + length]
        require(payload[:8] == b"\x89PNG\r\n\x1a\n" and payload[12:16] == b"IHDR", "PNG header invalid")
        width, height = struct.unpack_from(">II", payload, 16)
        require(0 < width <= 4096 and 0 < height <= 4096, "Image dimensions exceed trial bounds")
        images.append({"name": image.get("name"), "width": width, "height": height, "bytes": length, "sha256": digest(payload)})
    vertices = triangles = 0
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            require(primitive.get("mode", 4) == 4 and not primitive.get("targets"), "Expected static triangles")
            require({"POSITION", "TEXCOORD_0"} <= set(primitive["attributes"]), "Position or UV missing")
            vertices += doc["accessors"][primitive["attributes"]["POSITION"]]["count"]
            count = doc["accessors"][primitive["indices"]]["count"] if "indices" in primitive else doc["accessors"][primitive["attributes"]["POSITION"]]["count"]
            require(count % 3 == 0, "Triangle index count invalid")
            triangles += count // 3
    require(vertices <= 500000 and triangles <= 500000, "Geometry exceeds trial limits")
    return doc, {"sha256": digest(data), "bytes": len(data), "images": images, "accessorVertices": vertices, "primitiveTriangles": triangles}


def material_metadata(doc):
    materials = []
    for material in doc.get("materials", []):
        pbr = material.get("pbrMetallicRoughness", {})
        materials.append({
            "name": material.get("name"), "doubleSided": material.get("doubleSided", False),
            "alphaMode": material.get("alphaMode", "OPAQUE"), "alphaCutoff": material.get("alphaCutoff", 0.5),
            "baseColorFactor": pbr.get("baseColorFactor", [1, 1, 1, 1]),
            "metallicFactor": pbr.get("metallicFactor", 1), "roughnessFactor": pbr.get("roughnessFactor", 1),
            "emissiveFactor": material.get("emissiveFactor", [0, 0, 0]),
            "baseColorTexCoord": pbr.get("baseColorTexture", {}).get("texCoord", 0),
            "hasBaseColorTexture": "baseColorTexture" in pbr,
            "normalTexture": material.get("normalTexture"), "occlusionTexture": material.get("occlusionTexture"),
            "extensions": material.get("extensions", {}),
        })
    require(len({item["name"] for item in materials}) == len(materials), "Ambiguous material names")
    return sorted(materials, key=lambda item: item["name"] or "")


def close_values(before, after, label):
    if isinstance(before, (int, float)) and not isinstance(before, bool):
        require(isinstance(after, (int, float)) and math.isfinite(before) and math.isfinite(after) and abs(before - after) <= 1e-5, label)
    elif isinstance(before, dict):
        require(isinstance(after, dict) and set(before) == set(after), label)
        for key in before:
            close_values(before[key], after[key], label)
    elif isinstance(before, list):
        require(isinstance(after, list) and len(before) == len(after), label)
        for first, second in zip(before, after):
            close_values(first, second, label)
    else:
        require(before == after, label)


def reset_import(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if bpy.context.scene.world is None:
        bpy.context.scene.world = bpy.data.worlds.new("Private trial world")
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    require(not bpy.data.actions and all(obj.type in {"MESH", "EMPTY"} for obj in bpy.context.scene.objects), "Unexpected animated or non-woodland object")


def quantized(values):
    result = []
    for value in values:
        require(math.isfinite(float(value)), "Non-finite geometry/UV")
        result.append(round(float(value), 5))
    return tuple(result)


def geometry_snapshot():
    objects = []
    world_points = []
    for obj in sorted(bpy.context.scene.objects, key=lambda value: value.name):
        item = {"name": obj.name, "type": obj.type, "parent": obj.parent.name if obj.parent else None,
                "worldMatrix": [[float(value) for value in row] for row in obj.matrix_world]}
        if obj.type == "MESH":
            mesh = obj.data
            mesh.calc_loop_triangles()
            require(mesh.vertices and mesh.uv_layers and mesh.uv_layers.active, "Untextured or empty mesh")
            local_vertices = sorted(quantized(vertex.co) for vertex in mesh.vertices)
            triangles = []
            for triangle in mesh.loop_triangles:
                corners = []
                for vertex_index, loop_index in zip(triangle.vertices, triangle.loops):
                    corner = [quantized(mesh.vertices[vertex_index].co)]
                    corner.extend(quantized(layer.data[loop_index].uv) for layer in mesh.uv_layers)
                    corners.append(tuple(corner))
                # Cyclic rotation preserves winding while permitting index renumbering.
                rotations = [tuple(corners[index:] + corners[:index]) for index in range(3)]
                material = mesh.materials[triangle.material_index].name if mesh.materials else None
                triangles.append((material, min(rotations)))
            points = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
            world_points.extend(points)
            item.update(vertices=len(mesh.vertices), triangles=len(mesh.loop_triangles),
                uvLayers=[layer.name for layer in mesh.uv_layers], uvLoops=[len(layer.data) for layer in mesh.uv_layers],
                materialSlots=[material.name if material else None for material in mesh.materials],
                vertexSignature=digest(json.dumps(local_vertices).encode()), triangleUvSignature=digest(json.dumps(sorted(triangles)).encode()),
                bounds={"min": [min(point[axis] for point in points) for axis in range(3)],
                        "max": [max(point[axis] for point in points) for axis in range(3)]})
        objects.append(item)
    require(world_points, "No woodland geometry")
    return {"objects": objects, "vertices": sum(item.get("vertices", 0) for item in objects),
            "triangles": sum(item.get("triangles", 0) for item in objects),
            "bounds": {"min": [min(point[axis] for point in world_points) for axis in range(3)],
                       "max": [max(point[axis] for point in world_points) for axis in range(3)]}}


def binary_payload(data):
    offset = 12
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        if kind == 0x004E4942:
            return data[offset:offset + length]
        offset += length
    raise ValueError("Embedded binary missing")


def view_payloads(doc, binary):
    declared = doc["buffers"][0]["byteLength"]
    require(type(declared) is int and 0 <= declared <= len(binary) and len(binary) - declared <= 3, "Invalid binary length")
    records = []
    for index, view in enumerate(doc.get("bufferViews", [])):
        start, length = view.get("byteOffset", 0), view["byteLength"]
        require(type(start) is int and type(length) is int and view.get("buffer", 0) == 0
                and start >= 0 and start % 4 == 0 and length > 0 and start + length <= declared, "Invalid buffer view")
        records.append((start, start + length, index))
    ordered = sorted(records)
    require(ordered and all(left[1] <= right[0] for left, right in zip(ordered, ordered[1:])), "Overlapping buffer views refused")
    return {index: binary[start:end] for start, end, index in ordered}, ordered


def require_repack_identity(before, after, binary_before, binary_after):
    original, _ = view_payloads(before, binary_before)
    candidate, _ = view_payloads(after, binary_after)
    image_views = {image["bufferView"] for image in before["images"]}
    require(set(original) == set(candidate), "Buffer view count changed")
    expected = copy.deepcopy(before)
    expected["buffers"][0]["byteLength"] = after["buffers"][0]["byteLength"]
    evidence = []
    for index, view in enumerate(expected["bufferViews"]):
        view["byteOffset"] = after["bufferViews"][index].get("byteOffset", 0)
        if index in image_views:
            view["byteLength"] = after["bufferViews"][index]["byteLength"]
        else:
            require(original[index] == candidate[index], "Non-image buffer payload changed")
            evidence.append({"bufferView": index, "bytes": len(original[index]), "sha256": digest(original[index])})
    require(expected == after, "Non-layout glTF JSON semantics changed")
    return evidence


def repack_images(doc, binary, replacements):
    payloads, ordered = view_payloads(doc, binary)
    image_views = {image["bufferView"] for image in doc["images"]}
    require(set(replacements) == image_views and image_views <= set(payloads), "Image replacement set changed")
    # An image view must never also supply vertex/index/sparse accessor data.
    for accessor in doc.get("accessors", []):
        referenced = {accessor["bufferView"]} if "bufferView" in accessor else set()
        for part in accessor.get("sparse", {}).values():
            if isinstance(part, dict) and "bufferView" in part:
                referenced.add(part["bufferView"])
        require(not referenced & image_views, "Image shares geometry buffer view")
    after = copy.deepcopy(doc)
    packed = bytearray()
    for _, _, index in ordered:
        packed.extend(b"\0" * (-len(packed) % 4))
        view = after["bufferViews"][index]
        view["byteOffset"] = len(packed)
        payload = replacements[index] if index in image_views else payloads[index]
        require(type(payload) is bytes and len(payload) <= MAX_FILE, "Replacement payload invalid")
        if index in image_views:
            require(len(payload) >= 24, "Replacement image payload invalid")
        view["byteLength"] = len(payload)
        packed.extend(payload)
    after["buffers"][0]["byteLength"] = len(packed)
    packed.extend(b"\0" * (-len(packed) % 4))
    encoded = json.dumps(after, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    total = 12 + 8 + len(encoded) + 8 + len(packed)
    require(total <= MAX_FILE, "Candidate exceeds bounded GLB size")
    result = (struct.pack("<4sII", b"glTF", 2, total) + struct.pack("<II", len(encoded), 0x4E4F534A)
              + encoded + struct.pack("<II", len(packed), 0x004E4942) + bytes(packed))
    require_repack_identity(doc, after, binary, bytes(packed))
    return result


def texture_variant(doc, baseline_bytes, output):
    binary = binary_payload(baseline_bytes)
    payloads, _ = view_payloads(doc, binary)
    replacements = {}
    for index, metadata in enumerate(doc["images"]):
        view = metadata["bufferView"]
        if view in replacements:
            continue
        source = output / f"texture-{index:02d}-original.png"
        scaled = output / f"texture-{index:02d}-{TEXTURE_DIMENSION}.png"
        with source.open("xb") as stream:
            stream.write(payloads[view])
        image = bpy.data.images.load(str(source), check_existing=False)
        require(image.size[0] > 0 and image.size[1] > 0 and image.channels in {3, 4}, "Unsupported texture")
        image.scale(TEXTURE_DIMENSION, TEXTURE_DIMENSION)
        image.filepath_raw = str(scaled)
        image.file_format = "PNG"
        image.save()
        image.pack()
        require(image.packed_file is not None, "Scaled image was not packed")
        payload = bytes(image.packed_file.data)
        require(payload[:8] == b"\x89PNG\r\n\x1a\n" and payload[12:16] == b"IHDR"
                and struct.unpack_from(">II", payload, 16) == (TEXTURE_DIMENSION, TEXTURE_DIMENSION), "Packed texture is not requested dimensions PNG")
        replacements[view] = payload
        bpy.data.images.remove(image)
    require(replacements and len(replacements) <= 32, "No bounded image variant")
    return repack_images(doc, binary, replacements)


def render(path, destination, setup_render):
    reset_import(path)
    scene = setup_render(environment=True)
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 32
    scene.cycles.seed = SEED
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = False
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 2
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(destination)
    bpy.ops.render.render(write_still=True)
    require(destination.is_file() and destination.stat().st_size <= MAX_FILE, "Preview missing or oversized")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    global TEXTURE_DIMENSION
    parser.add_argument("--max-dimension", type=int, choices=(128, 256, 384, 512), required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-script", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    TEXTURE_DIMENSION = args.max_dimension
    baseline = args.baseline.absolute()
    verify = args.verify_script.absolute()
    output = args.output.absolute()
    require(not baseline.is_symlink() and not verify.is_symlink(), "Input symlinks refused")
    baseline, verify = baseline.resolve(strict=True), verify.resolve(strict=True)
    require(not os.path.lexists(output), "Output must be fresh")
    require(output.parent.is_dir() and not output.parent.is_symlink(), "Output parent must exist")
    output = output.parent.resolve(strict=True) / output.name
    require(not output.is_relative_to(baseline.parent) and not baseline.parent.is_relative_to(output), "Output overlaps baseline folder")
    require(not output.is_relative_to(verify.parent) and not verify.is_relative_to(output), "Output overlaps trusted code")
    for parent in (output.parent, *output.parent.parents):
        require(not (parent / ".git").exists(), "Output must remain outside Git")
    require(bpy.app.version[:2] == (4, 1), "Trial requires reviewed Blender4.1.x API")
    baseline_bytes = input_bytes(baseline)
    verify_bytes = input_bytes(verify)
    require(digest(verify_bytes) == VERIFY_HASH, "Verify helper differs from reviewed af2cc source")
    doc_before, glb_before = glb(baseline)
    require(glb_before["sha256"] == digest(baseline_bytes), "Baseline changed before import")
    require(any(item["alphaMode"] == "MASK" and item["doubleSided"] for item in material_metadata(doc_before)), "Reviewed MASK/double-sided foliage missing")
    os.umask(0o077)
    output.mkdir(mode=0o700)
    candidate = output / f"woodland-{TEXTURE_DIMENSION}.glb"
    reset_import(baseline)
    before = geometry_snapshot()
    # Scale with Blender, then replace only embedded image payloads in the
    # original GLB. Re-exporting its mesh would change importer vertex splits.
    candidate_bytes = texture_variant(doc_before, baseline_bytes, output)
    with candidate.open("xb") as stream:
        stream.write(candidate_bytes)
    os.chmod(candidate, 0o600)
    doc_after, glb_after = glb(candidate)
    require(glb_before["primitiveTriangles"] == glb_after["primitiveTriangles"] and
            glb_before["accessorVertices"] == glb_after["accessorVertices"], "glTF primitive structure changed")
    require(len(glb_before["images"]) == len(glb_after["images"]), "Embedded texture count changed")
    non_image_views = require_repack_identity(doc_before, doc_after, binary_payload(baseline_bytes), binary_payload(candidate_bytes))
    require(all(item["width"] == item["height"] == TEXTURE_DIMENSION for item in glb_after["images"]), "Candidate textures are not requested dimensions")
    close_values(material_metadata(doc_before), material_metadata(doc_after), "Material alpha/tint/texture properties changed")
    reset_import(candidate)
    after = geometry_snapshot()
    close_values(before, after, "Geometry/object/UV/material-slot regression")
    require(input_bytes(baseline) == baseline_bytes and input_bytes(verify) == verify_bytes, "Read-only inputs changed")
    report = {"schemaVersion": 1, "status": "passed", "scope": "private_evaluation", "blenderVersion": bpy.app.version_string,
        "sourceCommit": "af2cc2c2356acdaca7ede97825740eebc1e243a1", "geometryPreserved": True, "maxDimension": TEXTURE_DIMENSION,
        "baseline": glb_before, "candidate": glb_after, "geometry": {"baseline": before, "candidate": after},
        "nonImageBufferViews": non_image_views, "originalJsonSemanticsPreserved": True,
        "materials": {"baseline": material_metadata(doc_before), "candidate": material_metadata(doc_after)},
        "fileBytesSaved": glb_before["bytes"] - glb_after["bytes"],
        "render": {"engine": "CYCLES", "device": "CPU", "threads": 2, "pixels": [512, 512], "samples": 32, "seed": SEED,
                   "identicalSetup": True, "previews": [], "performed": False},
        "limitations": ["No phone or WebGL performance validation", "Texture appearance requires owner comparison", "No publication or license-delivery approval"]}
    (output / "comparison.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("ABBY_PRIVATE_WOODLAND_TRIAL", json.dumps({"status": "passed", "geometryPreserved": True,
        "baselineBytes": glb_before["bytes"], "candidateBytes": glb_after["bytes"], "triangles": before["triangles"]}))


if __name__ == "__main__":
    main()
