"""Private Blender worker for the publisher's existing modular Archer art."""
import json
import math
from pathlib import Path
import re
import sys

import bpy
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree


def reset():
    # glTF import creates hidden custom bone-shape objects. Selection-based
    # deletion misses them and can carry them into the next costume export.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def import_fbx(path, use_anim=False):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(path), use_anim=use_anim)
    return list(set(bpy.context.scene.objects) - before)


def material(name, texture):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    bsdf = result.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Roughness'].default_value = 0.9
    image = result.node_tree.nodes.new('ShaderNodeTexImage')
    image.image = bpy.data.images.load(str(texture), check_existing=True)
    result.node_tree.links.new(image.outputs['Color'], bsdf.inputs['Base Color'])
    result.node_tree.links.new(image.outputs['Alpha'], bsdf.inputs['Alpha'])
    if bpy.app.version < (4, 2, 0):
        result.blend_method = 'CLIP'
        result.alpha_threshold = 0.5
    else:
        result.surface_render_method = 'DITHERED'
        # Preserve the accepted alpha cutout instead of enabling transparency.
        cutoff = result.node_tree.nodes.new('ShaderNodeMath')
        cutoff.operation = 'GREATER_THAN'
        cutoff.inputs[1].default_value = 0.5
        result.node_tree.links.new(image.outputs['Alpha'], cutoff.inputs[0])
        result.node_tree.links.new(cutoff.outputs[0], bsdf.inputs['Alpha'])
    result.use_backface_culling = False
    return result


def bounds(meshes):
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    vertices = [obj.matrix_world @ vertex.co for obj in meshes for vertex in obj.evaluated_get(graph).data.vertices]
    if not vertices or not all(math.isfinite(component) for vertex in vertices for component in vertex):
        raise ValueError('Invalid Archer geometry')
    return Vector([min(vertex[i] for vertex in vertices) for i in range(3)]), Vector([max(vertex[i] for vertex in vertices) for i in range(3)])


def setup_render():
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if bpy.app.version >= (4, 2, 0) else 'BLENDER_EEVEE'
    scene.render.resolution_x = 512
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    if scene.world is None:
        scene.world = bpy.data.worlds.new('Archer Review World')
    scene.world.color = (0.55, 0.65, 0.8)
    scene.view_settings.view_transform = 'Standard'
    for location, energy in (((3, -4, 5), 450), ((-3, 2, 4), 250)):
        bpy.ops.object.light_add(type='AREA', location=location)
        bpy.context.object.data.energy = energy
        bpy.context.object.data.size = 5
    bpy.ops.object.camera_add(location=(0, -5, 2.4))
    camera = bpy.context.object
    camera.data.lens = 65
    camera.rotation_euler = (Vector((0, 0, 0.95)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    scene.camera = camera
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.015))
    floor = bpy.context.object
    floor.data.materials.append(bpy.data.materials.new('Evidence floor'))
    floor.data.materials[0].diffuse_color = (0.85, 0.8, 0.65, 1)
    return scene


def review_hair_hidden(name, headwear, hairstyle):
    """Match runtime hair selection: only the hood substitutes hat hair."""
    if name == 'Archer_Hair_For_Hat':
        return headwear != 'hood-mystical'
    return headwear == 'hood-mystical' or name != hairstyle


def at_frame(frame):
    whole = math.floor(frame)
    bpy.context.scene.frame_set(whole, subframe=frame - whole)
    bpy.context.view_layer.update()


def vertices(mesh, surface_only=False):
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = mesh.evaluated_get(graph)
    used = {index for polygon in evaluated.data.polygons for index in polygon.vertices} if surface_only else None
    result = [mesh.matrix_world @ vertex.co for vertex in evaluated.data.vertices if used is None or vertex.index in used]
    if not result or not all(math.isfinite(value) for vertex in result for value in vertex):
        raise ValueError('Supplied Idle produces invalid vertices')
    return result


def vertex_error(first, second):
    if len(first) != len(second):
        raise ValueError('Runtime export changed the supplied vertex layout')
    return max((left - right).length for left, right in zip(first, second))


def surface_error(first, second):
    """Compare geometry despite glTF's required splitting at UV seams."""
    def furthest(points, reference):
        tree = KDTree(len(reference))
        for index, point in enumerate(reference):
            tree.insert(point, index)
        tree.balance()
        return max(tree.find(point)[2] for point in points)
    return max(furthest(first, second), furthest(second, first))


def uv_values(mesh):
    if not mesh.data.uv_layers.active:
        raise ValueError('Archer module has no supplied UVs')
    return tuple(tuple(value.uv) for value in mesh.data.uv_layers.active.data)


def rigid_scale(matrix):
    """Reject shear, reflection and nonuniform rest scale before pose mapping."""
    location, rotation, scale = matrix.decompose()
    if not all(math.isfinite(value) for row in matrix for value in row) or min(scale) <= 0:
        raise ValueError('Archer rig contains invalid or reflected transforms')
    if max(scale) - min(scale) > 0.00001:
        raise ValueError('Archer rig has incompatible nonuniform scale')
    rebuilt = Matrix.LocRotScale(location, rotation, scale)
    if max(abs(left - right) for row, other in zip(matrix, rebuilt) for left, right in zip(row, other)) > 0.00001:
        raise ValueError('Archer rig contains shear')
    return scale.x


def matching_rest_rigs(source, target):
    """Validate common bone identities, topology and scale; measure proportions.

    The publisher's humanoid Idle has different segment lengths from its
    costumes. Retarget rotations through the original target hierarchy instead
    of copying translations or stretching that hierarchy to match the source.
    The returned positional difference is diagnostic, never a matching claim.
    """
    source_bones = source.data.bones
    target_bones = target.data.bones
    if set(source_bones.keys()) != set(target_bones.keys()):
        raise ValueError('Supplied Idle and costume have different bone identities')
    worst = 0.0
    for bone in source_bones:
        other = target_bones[bone.name]
        if (bone.parent.name if bone.parent else None) != (other.parent.name if other.parent else None):
            raise ValueError('Supplied Idle and costume have different bone topology')
        source_world = source.matrix_world @ bone.matrix_local
        target_world = target.matrix_world @ other.matrix_local
        if abs(rigid_scale(source_world) - rigid_scale(target_world)) > 0.00001:
            raise ValueError('Supplied Idle and costume have different rig scales')
        for source_joint, target_joint in ((bone.head_local, other.head_local), (bone.tail_local, other.tail_local)):
            worst = max(worst, (source.matrix_world @ source_joint - target.matrix_world @ target_joint).length)
    return worst


def constant_unreferenced_transform(obj, objects):
    """Accept an export helper only when it contributes no supplied motion."""
    if obj.type != 'EMPTY' or obj.parent or obj.children or obj.constraints:
        return False
    for other in objects:
        if other.animation_data and other.animation_data.drivers:
            return False
        if any(getattr(modifier, 'object', None) == obj for modifier in other.modifiers):
            return False
        if any(getattr(constraint, 'target', None) == obj for constraint in other.constraints):
            return False
    for curve in obj.animation_data.action.fcurves:
        if curve.data_path not in ('location', 'rotation_euler', 'rotation_quaternion', 'scale') or curve.modifiers:
            return False
        points = list(curve.keyframe_points)
        if not points:
            return False
        value = points[0].co.y
        for point in points:
            if point.interpolation not in ('CONSTANT', 'LINEAR', 'BEZIER'):
                return False
            if any(not math.isfinite(sample) or abs(sample - value) > 0.0000001
                   for sample in (point.co.y, point.handle_left.y, point.handle_right.y)):
                return False
    return True


def supplied_idle(source):
    armatures = [obj for obj in source if obj.type == 'ARMATURE']
    if len(armatures) != 1:
        raise ValueError('Supplied Idle must have one identifiable source rig')
    armature = armatures[0]
    action = armature.animation_data.action if armature.animation_data else None
    if action is None:
        raise ValueError('Supplied Idle has no armature take')
    for obj in source:
        if obj == armature or not obj.animation_data or not obj.animation_data.action:
            continue
        if not constant_unreferenced_transform(obj, source):
            raise ValueError('Supplied Idle contains extra animated objects')
    for curve in action.fcurves:
        match = re.fullmatch(r'pose\.bones\["([^"\\]+)"\]\.(location|rotation_euler|rotation_quaternion|scale)', curve.data_path)
        if not match or match.group(1) not in armature.data.bones:
            raise ValueError('Supplied Idle contains unhandled animation tracks')
    start, end = action.frame_range
    if not math.isfinite(start + end) or not 0 < end - start <= 600:
        raise ValueError('Supplied Idle has no bounded positive duration')
    frames = {start, end, (start + end) / 2}
    frames.update(float(frame) for frame in range(math.ceil(start), math.floor(end) + 1))
    frames.update(point.co.x for curve in action.fcurves for point in curve.keyframe_points)
    if len(frames) > 1200 or any(not start <= frame <= end for frame in frames):
        raise ValueError('Supplied Idle keys exceed its bounded frame range')
    return armature, action, sorted(frames)


def attach_head_module(mesh, armature, head_bone):
    if mesh.modifiers or mesh.vertex_groups:
        raise ValueError('Head module needs explicit review of its existing skin')
    rest = vertices(mesh)
    before_uv = uv_values(mesh)
    world = mesh.matrix_world.copy()
    mesh.parent = armature
    mesh.matrix_world = world
    group = mesh.vertex_groups.new(name=head_bone)
    group.add(list(range(len(mesh.data.vertices))), 1.0, 'REPLACE')
    modifier = mesh.modifiers.new(name='Supplied Head Attachment', type='ARMATURE')
    modifier.object = armature
    armature.data.bones[head_bone].use_deform = True
    bpy.context.view_layer.update()
    if vertex_error(rest, vertices(mesh)) > 0.000001 or before_uv != uv_values(mesh):
        raise ValueError('Head attachment changed the supplied rest geometry or UVs')
    return rest


def attach_wardrobe_module(mesh, armature, attachment):
    """Place an unchanged supplied mesh using its actual publisher socket."""
    bone = attachment['bone']
    if bone not in armature.data.bones:
        raise ValueError('Wardrobe prefab joint is absent from its complete costume rig')
    position = (armature.matrix_world @ armature.data.bones[bone].matrix_local).translation
    if (position - Vector(attachment['bone_position'])).length > 0.0001:
        raise ValueError('Wardrobe prefab joint differs from its actual costume rest joint')
    socket = Matrix(attachment['world_matrix'])
    scale = rigid_scale(socket)
    if abs(scale - 1) > 0.00001:
        raise ValueError('Wardrobe socket changes supplied module scale')
    original_geometry = [vertex.co.copy() for vertex in mesh.data.vertices]
    original_uv = uv_values(mesh)
    mesh.matrix_world = socket @ Matrix.Rotation(math.pi / 2, 4, 'X') @ mesh.matrix_world
    # FBX can contain a slightly posed palm even with animation import off.
    # Check the unchanged source at REST, then restore its actual pose. This
    # changes no joint/rest matrices, original geometry or animation keys.
    position_mode = armature.data.pose_position
    try:
        armature.data.pose_position = 'REST'
        bpy.context.view_layer.update()
        rest = attach_head_module(mesh, armature, bone)
    finally:
        armature.data.pose_position = position_mode
        bpy.context.view_layer.update()
    if original_geometry != [vertex.co for vertex in mesh.data.vertices] or original_uv != uv_values(mesh):
        raise ValueError('Wardrobe attachment changed supplied geometry or UVs')
    return rest


def convert_supplied_motion(source, target, frames):
    rest_difference = matching_rest_rigs(source, target)
    source_rest = {bone.name: source.matrix_world @ bone.matrix_local for bone in source.data.bones}
    target_rest = {bone.name: target.matrix_world @ bone.matrix_local for bone in target.data.bones}
    ordered = sorted(target.pose.bones, key=lambda bone: len(bone.parent_recursive))
    measurements = {
        'source_rest_joint_difference': rest_difference,
        'target_joint_error': 0.0, 'rotation_delta_error': 0.0,
        'nonroot_translation_variation': 0.0, 'source_scale_variation': 0.0,
    }
    source_poses = {}
    initial_translations = {}
    # Inspect the complete source before writing any target keys. Humanoid
    # rotation retargeting must not silently discard animated child offsets or
    # scale. Tiny import roundoff is measured in world meters / unit scale.
    for frame in frames:
        at_frame(frame)
        source_poses[frame] = {}
        for bone in source.pose.bones:
            pose = source.matrix_world @ bone.matrix
            rigid_scale(pose)
            source_poses[frame][bone.name] = pose.copy()
            scale_error = max(abs(value - 1) for value in bone.matrix_basis.to_scale())
            measurements['source_scale_variation'] = max(measurements['source_scale_variation'], scale_error)
            if bone.parent:
                translation = (source.matrix_world @ source.data.bones[bone.name].matrix_local).to_3x3() @ bone.matrix_basis.translation
                first = initial_translations.setdefault(bone.name, translation.copy())
                measurements['nonroot_translation_variation'] = max(measurements['nonroot_translation_variation'], (translation - first).length)
        if measurements['source_scale_variation'] > 0.00001:
            raise ValueError('Supplied Idle changes the accepted rig scale')
        if measurements['nonroot_translation_variation'] > 0.00001:
            raise ValueError('Supplied Idle animates nonroot joint translations')
    expected = {}
    previous = {}
    for frame in frames:
        at_frame(frame)
        expected[frame] = {}
        target_poses = {}
        for bone in ordered:
            name = bone.name
            source_pose = source_poses[frame][name]
            source_delta = source_pose.to_quaternion() @ source_rest[name].to_quaternion().inverted()
            rotation = source_delta @ target_rest[name].to_quaternion()
            if bone.parent:
                parent = bone.parent.name
                parent_delta = target_poses[parent].to_quaternion() @ target_rest[parent].to_quaternion().inverted()
                location = target_poses[parent].translation + parent_delta @ (target_rest[name].translation - target_rest[parent].translation)
            else:
                location = target_rest[name].translation + source_pose.translation - source_rest[name].translation
            world_pose = Matrix.LocRotScale(location, rotation, target_rest[name].to_scale())
            target_poses[name] = world_pose
            expected[frame][name] = world_pose @ target_rest[name].inverted()
            bone.matrix = target.matrix_world.inverted() @ world_pose
            bpy.context.view_layer.update()
            actual = target.matrix_world @ bone.matrix
            measurements['target_joint_error'] = max(measurements['target_joint_error'], (actual.translation - location).length)
            actual_delta = actual.to_quaternion() @ target_rest[name].to_quaternion().inverted()
            actual_delta.normalize()
            source_delta.normalize()
            sign = 1 if actual_delta.dot(source_delta) >= 0 else -1
            rotation_error = math.sqrt(sum((left - sign * right) ** 2 for left, right in zip(actual_delta, source_delta)))
            measurements['rotation_delta_error'] = max(measurements['rotation_delta_error'], rotation_error)
            location, rotation, scale = bone.matrix_basis.decompose()
            if bone.name in previous and previous[bone.name].dot(rotation) < 0:
                rotation.negate()
            previous[bone.name] = rotation.copy()
            bone.rotation_mode = 'QUATERNION'
            bone.location = location
            bone.rotation_quaternion = rotation
            bone.scale = scale
            for path in ('location', 'rotation_quaternion', 'scale'):
                bone.keyframe_insert(data_path=path, frame=frame, group=bone.name)
    for curve in target.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = 'LINEAR'
    if measurements['target_joint_error'] > 0.0001 or measurements['rotation_delta_error'] > 0.0001:
        raise ValueError('Supplied Idle retargeting changes target joints or supplied rotations')
    return measurements, expected


def one_mesh(objects, label):
    meshes = [obj for obj in objects if obj.type == 'MESH']
    if len(meshes) != 1:
        raise ValueError(f'{label} must contain exactly one reviewed mesh')
    return meshes[0]


def export_modular(path):
    """Keep supplied influences and begin the reviewed loop at exactly zero."""
    bpy.ops.export_scene.gltf(
        filepath=str(path), export_format='GLB', export_yup=True,
        export_animations=True, export_animation_mode='ACTIONS',
        export_nla_strips=False, export_anim_single_armature=True,
        export_anim_slide_to_zero=True, export_skins=True,
        export_all_influences=True, export_materials='EXPORT',
        export_cameras=False, export_lights=False,
    )


def prepare_modular(config):
    source, output, evidence = (Path(config[key]) for key in ('source', 'output', 'evidence'))
    inventory, textures = config['source_map'], config['textures']
    evidence.mkdir(parents=True, exist_ok=True)
    reports = {}
    wardrobe_reports = {}
    for style, filename in inventory['bodies'].items():
        reset()
        objects = import_fbx(source / filename)
        body = one_mesh(objects, 'Costume')
        body.name = 'Archer_Body'
        armatures = [obj for obj in objects if obj.type == 'ARMATURE']
        if len(armatures) != 1:
            raise ValueError('Costume must retain its one supplied rig')
        rig = armatures[0]
        rig.name = 'Archer Rig'
        head_bone = inventory['head_bone']
        if head_bone not in rig.data.bones:
            raise ValueError('Reviewed head joint is absent from costume rig')
        if not 1.0 < (rig.matrix_world @ rig.data.bones[head_bone].head_local).z < 2.0:
            raise ValueError('Reviewed head joint is outside the supplied head region')
        original_body_uv = uv_values(body)
        body.data.materials.clear()
        body.data.materials.append(material('Archer Outfit Runtime', output / textures['outfit'][f'{style}:fair:nature']))
        modules = {}
        module_bones = {}
        module_sources = [(f'Archer_Head_{index:02}', inventory['head'][key], 'outfit') for index, key in enumerate(('head-01', 'head-02'), 1)]
        module_sources.append(('Archer_Face', inventory['face'], 'face'))
        module_sources.extend((f'Archer_Hair_{index:02}', inventory['hair'][key], 'hair') for index, key in enumerate(('hair-01', 'hair-02', 'hair-03', 'hair-04'), 1))
        for name, path, group in module_sources:
            imported = import_fbx(source / path)
            mesh = one_mesh(imported, name)
            if any(obj.type == 'ARMATURE' for obj in imported):
                raise ValueError('Static head module unexpectedly includes a separate rig')
            mesh.name = name
            mesh.matrix_world = Matrix.Rotation(math.pi / 2, 4, 'X') @ mesh.matrix_world
            texture = textures[group][f'{style}:fair:nature' if group == 'outfit' else 'face-01:dark' if group == 'face' else 'dark']
            mesh.data.materials.clear()
            mesh.data.materials.append(material(name + ' Runtime', output / texture))
            modules[name] = attach_head_module(mesh, rig, head_bone)
            module_bones[name] = head_bone
            objects.extend(imported)
        base_meshes = [body, *(bpy.data.objects[name] for name in modules)]
        # Equipment never changes the already reviewed body normalization.
        low, high = bounds(base_meshes)
        if not 1.5 < high.z - low.z < 2 or abs(low.z) > 0.02:
            raise ValueError('Supplied costume modules do not form an upright body')
        wardrobe_styles = {}
        if config['schema_version'] == 3:
            wardrobe = inventory['wardrobe']
            choices = [('Archer_Hair_For_Hat', None, wardrobe['hair_for_hat'])]
            for group in ('headwear', 'mask', 'bow', 'quiver'):
                choices.extend(('Archer_' + key.replace('-', '_').title(), key, descriptor) for key, descriptor in wardrobe[group].items())
            for name, key, descriptor in choices:
                imported = import_fbx(source / descriptor['source'])
                mesh = one_mesh(imported, name)
                if any(obj.type == 'ARMATURE' for obj in imported):
                    raise ValueError('Wardrobe module unexpectedly includes a separate rig')
                mesh.name = name
                attachment = config['wardrobe_attachments'][style][descriptor['attachment']]
                modules[name] = attach_wardrobe_module(mesh, rig, attachment)
                module_bones[name] = attachment['bone']
                wardrobe_styles[name] = key
                texture = textures['hair']['dark'] if key is None else textures['wardrobe'][f'{key}:nature']
                mesh.data.materials.clear()
                mesh.data.materials.append(material(name + ' Runtime', output / texture))
                objects.extend(imported)
        meshes = [body, *(bpy.data.objects[name] for name in modules)]
        idle_objects = import_fbx(source / inventory['idle'], use_anim=True)
        idle_rig, source_action, frames = supplied_idle(idle_objects)
        retarget_measurements, expected = convert_supplied_motion(idle_rig, rig, frames)
        start, end = source_action.frame_range
        head_error = wardrobe_error = 0.0
        for frame in frames:
            at_frame(frame)
            for name, rest_vertices in modules.items():
                predicted = [expected[frame][module_bones[name]] @ point for point in rest_vertices]
                error = vertex_error(predicted, vertices(bpy.data.objects[name]))
                if module_bones[name] == head_bone:
                    head_error = max(head_error, error)
                if name in wardrobe_styles:
                    wardrobe_error = max(wardrobe_error, error)
        if max(head_error, wardrobe_error) > 0.0001 or original_body_uv != uv_values(body):
            raise ValueError('Supplied Idle loses rigid module attachment or body UVs')
        for obj in idle_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.actions.remove(source_action)
        rig.animation_data.action.name = 'Idle'
        container = bpy.data.objects.new('Prepared Archer', None)
        bpy.context.collection.objects.link(container)
        for obj in objects:
            if obj.parent not in objects:
                world = obj.matrix_world.copy()
                obj.parent = container
                obj.matrix_world = world
        container.scale = (1.8 / (high.z - low.z),) * 3
        container.location.z = -low.z * container.scale.z
        bpy.context.view_layer.update()
        exported_rest = {bone.name: rig.matrix_world @ bone.matrix_local for bone in rig.data.bones}
        exported_topology = {bone.name: bone.parent.name if bone.parent else None for bone in rig.data.bones}
        checks = (0, 0.25, 0.5, 0.75, 1)
        snapshots = {}
        joint_snapshots = {}
        for fraction in checks:
            at_frame(start + (end - start) * fraction)
            snapshots[fraction] = {mesh.name: vertices(mesh, surface_only=mesh.name in wardrobe_styles) for mesh in meshes}
            joint_snapshots[fraction] = {bone.name: rig.matrix_world @ bone.matrix for bone in rig.pose.bones}
            if any((point - previous).length > 1.0 for point, previous in zip(snapshots[fraction]['Archer_Body'], snapshots[0]['Archer_Body'])):
                raise ValueError('Supplied Idle produces excessive costume displacement')
        # Archer03 has one vertex with five supplied influences. Never let the
        # exporter silently drop its fifth weight; the avatar renderer accepts
        # the extra JOINTS_1/WEIGHTS_1 set with matching deformation checks.
        export_modular(output / f'{style}.glb')
        fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
        reset()
        bpy.ops.import_scene.gltf(filepath=str(output / f'{style}.glb'))
        runtime_rigs = [obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE']
        runtime_meshes = {obj.name: obj for obj in bpy.context.scene.objects if obj.type == 'MESH' and obj.name.startswith('Archer_')}
        if len(runtime_rigs) != 1 or set(runtime_meshes) != set(snapshots[0]):
            raise ValueError('Runtime export lost costume modules or its complete rig')
        runtime_rig = runtime_rigs[0]
        if {bone.name: bone.parent.name if bone.parent else None for bone in runtime_rig.data.bones} != exported_topology:
            raise ValueError('Runtime export changed the supplied bone identities or topology')
        runtime_rest = {bone.name: runtime_rig.matrix_world @ bone.matrix_local for bone in runtime_rig.data.bones}
        action = runtime_rigs[0].animation_data.action if runtime_rigs[0].animation_data else None
        if action is None:
            raise ValueError('Runtime export lost supplied Idle')
        runtime_start, runtime_end = action.frame_range
        if abs((runtime_end - runtime_start) / fps - (end - start) / fps) > 0.001:
            raise ValueError('Runtime Idle duration changed')
        worst = 0.0
        module_errors = {}
        moving = set()
        runtime_first = None
        for fraction in checks:
            at_frame(runtime_start + (runtime_end - runtime_start) * fraction)
            for bone in runtime_rig.pose.bones:
                actual_pose = runtime_rig.matrix_world @ bone.matrix
                expected_pose = joint_snapshots[fraction][bone.name]
                retarget_measurements['target_joint_error'] = max(retarget_measurements['target_joint_error'], (actual_pose.translation - expected_pose.translation).length)
                actual_rotation = actual_pose.to_quaternion() @ runtime_rest[bone.name].to_quaternion().inverted()
                expected_rotation = expected_pose.to_quaternion() @ exported_rest[bone.name].to_quaternion().inverted()
                actual_rotation.normalize()
                expected_rotation.normalize()
                sign = 1 if actual_rotation.dot(expected_rotation) >= 0 else -1
                error = math.sqrt(sum((left - sign * right) ** 2 for left, right in zip(actual_rotation, expected_rotation)))
                retarget_measurements['rotation_delta_error'] = max(retarget_measurements['rotation_delta_error'], error)
            for name, mesh in runtime_meshes.items():
                actual = vertices(mesh, surface_only=name in wardrobe_styles)
                error = surface_error(actual, snapshots[fraction][name])
                module_errors[name] = max(module_errors.get(name, 0), error)
                worst = max(worst, error)
                if name == 'Archer_Body':
                    if runtime_first is None:
                        runtime_first = actual
                    moving.update(index for index, (point, first) in enumerate(zip(actual, runtime_first)) if (point - first).length > 0.00001)
        if worst > 0.001 or not moving or retarget_measurements['target_joint_error'] > 0.0001 or retarget_measurements['rotation_delta_error'] > 0.0001:
            raise ValueError(f'Reimported supplied Idle fails geometry/motion checks: surface_error={worst:.9g}, moving_vertices={len(moving)}, target_joint_error={retarget_measurements["target_joint_error"]:.9g}, rotation_delta_error={retarget_measurements["rotation_delta_error"]:.9g}, module_errors={module_errors}')
        scene = setup_render()
        # Evidence renders are reproducible on headless CPU-only hosts too.
        # Runtime GLB materials and browser rendering are validated separately.
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 16
        if config['schema_version'] == 3:
            # Bow Vines contains six unused positions which belong to no face.
            # Keep source data unchanged; glTF contains its complete 456 faces.
            # Surface checks exclude only positions unused by every polygon.
            unused = {name: len(modules[name]) - len(snapshots[0][name]) for name in wardrobe_styles}
            wardrobe_reports[style] = {'module_count': 10, 'sampled_frames': len(frames), 'attachment_error': wardrobe_error, 'reimport_max_vertex_error': worst, 'source_geometry_and_uvs_preserved': True, 'joint_bindings': {name: module_bones[name] for name in wardrobe_styles}, 'unused_source_vertex_counts': unused}
            recipes = [('aqua', 'crown-eve', 'none', 'bow-myth', 'quiver-angel', 'light'), ('nature', 'none', 'none', 'bow-greenhorn', 'quiver-rook', 'dark'), ('fire', 'hood-mystical', 'mask-undercover', 'bow-vines', 'quiver-tale', 'brown'), ('dark', 'crown-eve', 'mask-undercover', 'bow-vines', 'quiver-angel', 'grey')]
            for index, (palette, headwear, mask, bow, quiver, color) in enumerate(recipes):
                skin = 'fair' if index % 2 == 0 else 'tan'
                selected = {headwear, mask, bow, quiver}
                for name, mesh in runtime_meshes.items():
                    mesh.hide_render = False
                    if name in wardrobe_styles:
                        key = wardrobe_styles[name]
                        mesh.hide_render = review_hair_hidden(name, headwear, f'Archer_Hair_{index % 4 + 1:02}') if key is None else key not in selected
                        texture = textures['hair'][color] if key is None else textures['wardrobe'][f'{key}:{palette}']
                    elif name.startswith('Archer_Hair_'):
                        mesh.hide_render = review_hair_hidden(name, headwear, f'Archer_Hair_{index % 4 + 1:02}')
                        texture = textures['hair'][color]
                    elif name == 'Archer_Face':
                        texture = textures['face'][f'face-{index % 3 + 1:02}:{color}']
                    else:
                        if name.startswith('Archer_Head_'):
                            mesh.hide_render = name != f'Archer_Head_{index % 2 + 1:02}'
                        texture = textures['outfit'][f'{style}:{skin}:{palette}']
                    mesh.data.materials.clear()
                    mesh.data.materials.append(material(name + ' Wardrobe Review', output / texture))
                for fraction in (0, 0.5):
                    at_frame(runtime_start + (runtime_end - runtime_start) * fraction)
                    scene.render.filepath = str(evidence / f'{style}-wardrobe-{palette}-{fraction}.png')
                    bpy.ops.render.render(write_still=True)
        for color in (() if config['schema_version'] == 3 else config.get('review_colors', ('dark', 'light', 'brown', 'orange', 'grey'))):
            index = ('dark', 'light', 'brown', 'orange', 'grey').index(color)
            # Include all four palettes and both skins, including the supplied
            # Tan Fire texture whose Archer03 prefab wrongly selects Fair.
            skin, palette = (('fair', 'nature'), ('tan', 'aqua'), ('fair', 'fire'), ('tan', 'dark'), ('tan', 'fire'))[index]
            for name, mesh in runtime_meshes.items():
                if name.startswith('Archer_Head_'):
                    mesh.hide_render = name != f'Archer_Head_{index % 2 + 1:02}'
                if name.startswith('Archer_Hair'):
                    mesh.hide_render = name != f'Archer_Hair_{index % 4 + 1:02}'
                    texture = textures['hair'][color]
                elif name == 'Archer_Face':
                    texture = textures['face'][f'face-{index % 3 + 1:02}:{color}']
                else:
                    texture = textures['outfit'][f'{style}:{skin}:{palette}']
                mesh.data.materials.clear()
                mesh.data.materials.append(material(name + ' Review', output / texture))
            for fraction in (0, 0.5):
                at_frame(runtime_start + (runtime_end - runtime_start) * fraction)
                scene.render.filepath = str(evidence / f'{style}-{color}-{fraction}.png')
                bpy.ops.render.render(write_still=True)
        reports[style] = {'method': 'supplied-hierarchy-rotation-retarget-v1', 'duration_seconds': (end - start) / fps, 'sampled_frames': len(frames), 'moving_vertices': len(moving), **retarget_measurements, 'head_attachment_error': head_error, 'reimport_max_vertex_error': worst}
    (evidence / 'validation.json').write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
    if config['schema_version'] == 3:
        (evidence / 'wardrobe-validation.json').write_text(json.dumps(wardrobe_reports, indent=2) + '\n', encoding='utf-8')


def main():
    config = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
    if config.get('schema_version') in (2, 3):
        return prepare_modular(config)
    source, output, evidence = (Path(config[key]) for key in ('source', 'output', 'evidence'))
    evidence.mkdir(parents=True, exist_ok=True)
    reset()
    objects = import_fbx(source / 'FBX/Female Archer 01.FBX')
    body = next(obj for obj in objects if obj.type == 'MESH')
    body.name = 'Archer_Body'
    body.data.materials.clear()
    body.data.materials.append(material('Archer Outfit Runtime', output / config['textures']['outfit']['fair:nature']))
    armature = next(obj for obj in objects if obj.type == 'ARMATURE')
    armature.name = 'Archer Rig'
    head_parts = []
    for name, filename, key in [('Archer_Head', 'Female Head 02', 'outfit'), ('Archer_Face', 'Female Face', 'face')]:
        imported = import_fbx(source / f'Standard Assets Files/FBX/{filename}.FBX')
        obj = next(obj for obj in imported if obj.type == 'MESH')
        obj.name = name
        obj.matrix_world = Matrix.Rotation(math.pi / 2, 4, 'X') @ obj.matrix_world
        texture = config['textures'][key]['fair:nature' if key == 'outfit' else 'dark']
        obj.data.materials.clear()
        obj.data.materials.append(material(name + ' Runtime', output / texture))
        objects.extend(imported)
        head_parts.append(obj)
    hair = []
    hair_material = material('Archer_Hair Runtime', output / config['textures']['hair']['dark'])
    for index in range(1, 5):
        imported = import_fbx(source / f'Standard Assets Files/FBX/Female Hair {index:02}.FBX')
        obj = next(obj for obj in imported if obj.type == 'MESH')
        obj.name = f'Archer_Hair_{index:02}'
        obj.matrix_world = Matrix.Rotation(math.pi / 2, 4, 'X') @ obj.matrix_world
        obj.data.materials.clear()
        obj.data.materials.append(hair_material)
        objects.extend(imported)
        hair.append(obj)
    # Modules are supplied in matching authored world coordinates. Preserve
    # that fit rather than inventing transforms, bone attachments or animation.
    # The body FBX imports in Z-up; static head/hair FBXs require only Y-up
    # basis conversion. The resulting girl faces the positive-Z Three camera.
    meshes = [obj for obj in objects if obj.type == 'MESH']
    low, high = bounds(meshes)
    if not 1.5 < high.z - low.z < 2 or abs(low.z) > 0.02:
        raise ValueError('Supplied Archer modules do not form an upright body')
    container = bpy.data.objects.new('Prepared Archer', None)
    bpy.context.collection.objects.link(container)
    for obj in objects:
        if obj.parent not in objects:
            matrix = obj.matrix_world.copy()
            obj.parent = container
            obj.matrix_world = matrix
    container.scale = (1.8 / (high.z - low.z),) * 3
    container.location.z = -low.z * container.scale.z
    bpy.ops.export_scene.gltf(filepath=str(output / 'archer.glb'), export_format='GLB', export_yup=True, export_animations=False, export_skins=True, export_materials='EXPORT', export_cameras=False, export_lights=False)
    # Reimport verifies the actual runtime export, not just the source scene.
    reset()
    bpy.ops.import_scene.gltf(filepath=str(output / 'archer.glb'))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH' and obj.name.startswith('Archer_')]
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE']
    if len(meshes) != 7 or len(armatures) != 1 or bpy.data.actions:
        raise ValueError('Export lost Archer modules or added unreviewed animation')
    low, high = bounds(meshes)
    if abs(low.z) > 0.002 or abs(high.z - 1.8) > 0.002:
        raise ValueError('Runtime Archer is not grounded/normalized')
    scene = setup_render()
    palettes = [('fair', 'nature', 'dark'), ('tan', 'aqua', 'light'), ('fair', 'fire', 'dark'), ('tan', 'dark', 'light')]
    reports = []
    for index, (skin, outfit, color) in enumerate(palettes, 1):
        for obj in meshes:
            if obj.name.startswith('Archer_Hair'):
                obj.hide_render = obj.name != f'Archer_Hair_{index:02}'
                texture = config['textures']['hair'][color]
            elif obj.name == 'Archer_Face':
                texture = config['textures']['face'][color]
            else:
                texture = config['textures']['outfit'][f'{skin}:{outfit}']
            # Each verification instance uses a fresh material so a hair/face
            # palette never overwrites the body's material or another module.
            obj.data.materials.clear()
            obj.data.materials.append(material(obj.name + ' Evidence', output / texture))
        scene.render.filepath = str(evidence / f'archer-hair-{index:02}.png')
        bpy.ops.render.render(write_still=True)
        reports.append({'hair_style': f'hair-{index:02}', 'skin_tone': skin, 'outfit': outfit, 'hair_color': color})
    triangles = sum(len(obj.data.polygons) for obj in meshes)
    (evidence / 'validation.json').write_text(json.dumps({'mesh_count': len(meshes), 'bone_count': len(armatures[0].data.bones), 'polygon_count': triangles, 'animation': False, 'grounded_height': high.z, 'verified_render_variants': reports}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
