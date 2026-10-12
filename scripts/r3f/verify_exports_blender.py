"""Reimport/render the private GLBs with Blender; evidence stays private.

Run through Blender's --python option, passing --directory and --evidence
after its -- separator. This checks actual animated skin deformation in
addition to the structural checks in prepare_meshtint.py. It is not a phone
performance or R3F/browser acceptance test.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def setup_render(environment=False):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 512
    scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.color = (0.55, 0.65, 0.8)
    scene.view_settings.view_transform = "Standard"
    for location, energy in (((3, -4, 5), 500), ((-3, 2, 4), 250)):
        bpy.ops.object.light_add(type="AREA", location=location)
        bpy.context.object.data.energy = energy
        bpy.context.object.data.size = 5
    bpy.ops.object.camera_add(location=(0, -11, 7) if environment else (0, -6, 2.5))
    camera = bpy.context.object
    camera.data.lens = 42 if environment else 52
    camera.rotation_euler = (Vector((0, 0, 1)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.15 if environment else -0.02))
    floor = bpy.context.object
    material = bpy.data.materials.new("Evidence background")
    material.diffuse_color = (0.85, 0.8, 0.65, 1)
    floor.data.materials.append(material)
    return scene


def reset():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    args.directory = args.directory.resolve()
    args.evidence = args.evidence.resolve()
    args.evidence.mkdir(parents=True, exist_ok=True)
    reports = {}
    manifest = json.loads((args.directory / "manifest.json").read_text(encoding="utf-8"))
    takes = []
    for model in ("chick", "bird"):
        entry = manifest["models"][model]
        takes.append((model, entry["file"]))
        for interaction, take in entry.get("interaction_clips", {}).items():
            takes.append((f"{model}-{interaction}", take["file"]))
    for model, filename in takes:
        reset()
        bpy.ops.import_scene.gltf(filepath=str(args.directory / filename))
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
        # A single glTF turn clip can reimport as an armature action plus an
        # object-root action. Both are part of that supplied take and must run.
        if not meshes or len(armatures) != 1 or not armatures[0].animation_data or not armatures[0].animation_data.action:
            raise ValueError("GLB did not preserve the reviewed animated skin")
        scene = setup_render()
        end = int(max(action.frame_range[1] for action in bpy.data.actions))
        frames = sorted(set((0, end // 2, end)))
        if len(frames) != 3:
            raise ValueError("GLB animation duration is too short")
        positions = []
        sampled_bounds = []
        for index, frame in enumerate(frames):
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            graph = bpy.context.evaluated_depsgraph_get()
            vertices = [obj.matrix_world @ vertex.co for obj in meshes for vertex in obj.evaluated_get(graph).data.vertices]
            if not all(math.isfinite(component) for vertex in vertices for component in vertex):
                raise ValueError("GLB skin produced non-finite vertices")
            positions.append(vertices)
            sampled_bounds.append({
                "frame": frame,
                "min": [min(vertex[axis] for vertex in vertices) for axis in range(3)],
                "max": [max(vertex[axis] for vertex in vertices) for axis in range(3)],
            })
            scene.render.filepath = str(args.evidence / f"{model}-frame-{frame}.png")
            bpy.ops.render.render(write_still=True)
        maximum = max((first - middle).length for first, middle in zip(positions[0], positions[1]))
        if maximum < 0.001:
            raise ValueError("GLB skin does not animate")
        reports[model] = {
            "frames": frames, "maximum_vertex_displacement": maximum,
            "bone_counts": [len(obj.data.bones) for obj in armatures],
            "sampled_bounds": sampled_bounds,
        }
    reset()
    bpy.ops.import_scene.gltf(filepath=str(args.directory / "woodland.glb"))
    bpy.context.view_layer.update()
    stems = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj.name.startswith("Tree 02") and "Leaves" not in obj.name]
    if len(stems) != 3:
        raise ValueError("Woodland is missing its three reviewed tree stems")
    for stem in stems:
        points = [stem.matrix_world @ Vector(corner) for corner in stem.bound_box]
        low = Vector([min(point[i] for point in points) for i in range(3)])
        high = Vector([max(point[i] for point in points) for i in range(3)])
        size = high - low
        if low.z < -0.001 or size.z < 3 * max(size.x, size.y):
            raise ValueError("Woodland tree orientation/grounding is incorrect")
    ground = next(obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj.name == "Ground 01 Soft Edge")
    image = next(node.image for node in ground.data.materials[0].node_tree.nodes if node.type == "TEX_IMAGE")
    pixels = list(image.pixels)
    width, height = image.size
    grass_area = surface_area = 0
    for polygon in ground.data.polygons:
        points = [ground.matrix_world @ ground.data.vertices[index].co for index in polygon.vertices]
        center_z = sum(point.z for point in points) / len(points)
        normal = (ground.matrix_world.inverted().transposed().to_3x3() @ polygon.normal).normalized()
        if abs(center_z) > 0.005 or normal.z < 0.9:
            continue
        area = (points[1] - points[0]).cross(points[2] - points[0]).length / 2
        uv = sum((ground.data.uv_layers.active.data[index].uv for index in polygon.loop_indices), Vector((0, 0))) / len(polygon.loop_indices)
        offset = ((int(uv.y * height) % height) * width + (int(uv.x * width) % width)) * 4
        surface_area += area
        if pixels[offset + 1] > pixels[offset] * 1.1:
            grass_area += area
    if surface_area < 1 or grass_area / surface_area < 0.7:
        raise ValueError("The ground's supplied green grass surface is not facing up")
    reports["woodland"] = {"upright_grounded_stems": len(stems), "upward_grass_fraction": grass_area / surface_area}
    scene = setup_render(environment=True)
    scene.render.filepath = str(args.evidence / "woodland.png")
    bpy.ops.render.render(write_still=True)
    (args.evidence / "render-validation.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    print("GLB_SAMPLED_VALIDATION", json.dumps(reports))  # noqa: T201 — CLI evidence summary


if __name__ == "__main__":
    main()
