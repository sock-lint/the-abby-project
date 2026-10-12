"""Blender worker for prepare_meshtint.py; never writes to purchased sources."""
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector


def reset():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def import_fbx(path):
    existing = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(path), use_anim=True)
    return list(set(bpy.context.scene.objects) - existing)


def bounds(objects):
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    corners = [obj.matrix_world @ Vector(corner) for obj in objects if obj.type == "MESH" for corner in obj.evaluated_get(graph).bound_box]
    if not corners:
        raise ValueError("No imported geometry")
    return Vector([min(c[i] for c in corners) for i in range(3)]), Vector([max(c[i] for c in corners) for i in range(3)])


def material(name, textures, colors=None):
    result = bpy.data.materials.new(name + " Runtime")
    result.use_nodes = True
    principled = result.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Roughness"].default_value = 0.9
    image = result.node_tree.nodes.new("ShaderNodeTexImage")
    image.image = bpy.data.images.load(textures[name], check_existing=True)
    if colors and name in colors:
        tint = result.node_tree.nodes.new("ShaderNodeMix")
        tint.data_type = "RGBA"
        tint.blend_type = "MULTIPLY"
        tint.inputs[0].default_value = 1
        tint.inputs[7].default_value = colors[name]
        result.node_tree.links.new(image.outputs["Color"], tint.inputs[6])
        result.node_tree.links.new(tint.outputs[2], principled.inputs["Base Color"])
    else:
        result.node_tree.links.new(image.outputs["Color"], principled.inputs["Base Color"])
    if "Leaves" in name:
        result.node_tree.links.new(image.outputs["Alpha"], principled.inputs["Alpha"])
        result.blend_method = "CLIP"
        result.alpha_threshold = 0.5
        result.use_backface_culling = False
    return result


def set_materials(objects, materials, default):
    for obj in objects:
        if obj.type != "MESH":
            continue
        if not obj.data.materials:
            obj.data.materials.append(materials[default])
        for index, original in enumerate(obj.data.materials):
            key = next((key for key in materials if key in original.name), default)
            # Raw FBX slots have publisher default names. Unity's authored
            # tree prefab assigns the foliage atlas to these named meshes.
            if "Leaves" in obj.name and "Tree 02 Leaves" in materials:
                key = "Tree 02 Leaves"
            obj.data.materials[index] = materials[key]


def normalize(objects, name, target_height=None, footprint=None, position=(0, 0, 0)):
    # Keep FBX hierarchy, bind transforms and supplied keys unchanged.
    bpy.context.scene.frame_set(1)
    low, high = bounds(objects)
    size = high - low
    container = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(container)
    for obj in objects:
        if obj.parent not in objects:
            matrix = obj.matrix_world.copy()
            obj.parent = container
            obj.matrix_world = matrix
    if target_height:
        container.scale = (target_height / size.z,) * 3
    elif footprint:
        container.scale = (footprint[0] / size.x, footprint[1] / size.y, footprint[2] / size.z)
    center = Vector(((low.x + high.x) / 2, (low.y + high.y) / 2, low.z))
    container.location = Vector(position) - Vector([center[i] * container.scale[i] for i in range(3)])
    return container


def export(path, animations, animation_mode="ACTIONS"):
    bpy.context.view_layer.update()
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format="GLB", export_yup=True,
        export_animations=animations, export_animation_mode=animation_mode,
        export_nla_strips=True, export_anim_single_armature=True,
        export_force_sampling=True, export_anim_slide_to_zero=True,
        export_skins=True, export_materials="EXPORT", export_image_format="AUTO",
        export_cameras=False, export_lights=False,
    )


def creature(key, entry, source, output, textures):
    reset()
    folder = source / (entry["form"] + " Cute Series") / "FBX"
    objects = import_fbx(folder / (entry["form"] + "@" + entry["idle"] + ".FBX"))
    armature = next(obj for obj in objects if obj.type == "ARMATURE")
    idle = armature.animation_data.action
    idle.name = entry["idle"]
    # Reject a moving root rather than silently throwing its motion away.
    for obj in objects:
        if obj.type == "ARMATURE" or not obj.animation_data:
            continue
        action = obj.animation_data.action
        for curve in action.fcurves if action else ():
            values = [point.co.y for point in curve.keyframe_points]
            if values and max(values) - min(values) > 0.001:
                raise ValueError("Reviewed idle has moving root transforms")
        obj.animation_data_clear()
    for action in list(bpy.data.actions):
        if action != idle:
            bpy.data.actions.remove(action)
    idle.use_fake_user = True
    track = armature.animation_data.nla_tracks.new()
    track.name = idle.name
    track.strips.new(idle.name, int(idle.frame_range[0]), idle)
    track.mute = True
    set_materials(objects, {entry["form"]: material(entry["form"], textures)}, entry["form"])
    container = normalize(objects, "Prepared " + entry["form"], target_height=entry["height"])
    bpy.context.view_layer.update()
    normalization = container.matrix_world.copy()
    report = {"frames": int(idle.frame_range[1] - idle.frame_range[0] + 1), "bones": len(armature.data.bones), "source_clip_unchanged": True, "root_motion": False}
    export(output / (key + ".glb"), True)
    reports = {entry["idle"]: report}
    for interaction, clip in entry.get("interactions", {}).items():
        reports[clip] = interaction_take(key, interaction, clip, entry, folder, output, textures, normalization)
    return reports


def interaction_take(key, interaction, clip, entry, folder, output, textures, normalization):
    """Keep each publisher take's complete rig and skin, including its bind pose.

    Jump/flight takes have different supplied rest bones. Copying their actions
    onto the idle rig deforms the jaw/legs. Export the original matching mesh and
    rig instead, under the idle's static normalization so artwork never changes
    size between actions. Bird turns include an animated non-armature root;
    matching NLA track names preserve it in the same glTF animation.
    """
    reset()
    objects = import_fbx(folder / (entry["form"] + "@" + clip + ".FBX"))
    armature = next(obj for obj in objects if obj.type == "ARMATURE")
    supplied = armature.animation_data.action
    start, end = supplied.frame_range
    root_motion = []
    for obj in objects:
        action = obj.animation_data.action if obj.animation_data else None
        if not action:
            continue
        if obj != armature:
            for curve in action.fcurves:
                values = [point.co.y for point in curve.keyframe_points]
                if values and max(values) - min(values) > 0.001:
                    # This accepted set contains turns, never translating takes.
                    if curve.data_path != "rotation_euler" or interaction not in ("left", "right"):
                        raise ValueError("Interaction has unreviewed root motion")
                    root_motion.append({"object": obj.name, "channel": curve.data_path, "axis": curve.array_index})
        track = obj.animation_data.nla_tracks.new()
        track.name = clip
        track.strips.new(action.name, int(action.frame_range[0]), action)
        obj.animation_data.action = None
    container = bpy.data.objects.new("Prepared " + entry["form"], None)
    bpy.context.collection.objects.link(container)
    for obj in objects:
        if obj.parent not in objects:
            matrix = obj.matrix_world.copy()
            obj.parent = container
            obj.matrix_world = matrix
    container.matrix_world = normalization
    bpy.context.scene.frame_set(int(start))
    set_materials(objects, {entry["form"]: material(entry["form"], textures)}, entry["form"])
    export(output / f"{key}-{interaction}.glb", True, animation_mode="NLA_TRACKS")
    return {
        "frames": int(end - start + 1), "bones": len(armature.data.bones),
        "source_clip_unchanged": True, "separate_supplied_rig": True,
        "normalization_matches_idle": True, "root_motion": root_motion,
    }


def woodland(source, output, textures, colors):
    reset()
    forest = source / "Forest Ruins Pack Cute Series" / "FBX"
    materials = {name: material(name, textures, colors) for name in ("Forest Ruins", "Tree 02 Leaves")}
    placements = [
        ("FBX 1.1/Ground 01 Soft Edge.FBX", "Ground", None, (9, 7, 0.25), (0, 0, -0.25)),
        ("Tree 02.FBX", "Tree left", 2.4, None, (-3, 1.7, 0)),
        ("Tree 02.FBX", "Tree right", 2.8, None, (3.1, 2, 0)),
        ("Tree 02.FBX", "Tree back", 2.3, None, (0.6, 2.8, 0)),
        ("Rock 01.FBX", "Rock left", 0.45, None, (-2.2, -0.8, 0)),
        ("Rock 01.FBX", "Rock right", 0.35, None, (2.5, -0.4, 0)),
        ("Mushroom 01.FBX", "Mushroom", 0.45, None, (-1.9, -1.25, 0)),
        ("Ancient Pillar 01.FBX", "Ruin", 1.0, None, (2, 1.8, 0)),
    ]
    for filename, name, height, footprint, position in placements:
        objects = import_fbx(forest / filename)
        for obj in objects:
            if obj.animation_data:
                obj.animation_data_clear()
        # Older static Forest exports retain Y-up in Blender. The version1.1
        # Ground FBX already imports a +90deg X basis transform into Z-up;
        # applying it again would put the grass on the island's side. Unity
        # prefab roots are identity in both cases. Creature rigs also already
        # import in Z-up and never pass through this scenery conversion.
        if filename != "FBX 1.1/Ground 01 Soft Edge.FBX":
            axis = Matrix.Rotation(math.pi / 2, 4, "X")
            for obj in objects:
                if obj.parent not in objects:
                    obj.matrix_world = axis @ obj.matrix_world
        bpy.context.view_layer.update()
        set_materials(objects, materials, "Forest Ruins")
        normalize(objects, name, target_height=height, footprint=footprint, position=position)
    export(output / "woodland.glb", False)


config = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text(encoding="utf-8"))
source, output = Path(config["source"]), Path(config["output"])
validation = {}
for key, entry in config["creatures"].items():
    validation[key] = creature(key, entry, source, output, config["textures"])
woodland(source, output, config["textures"], config["material_colors"])
(output / "skinning-validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
