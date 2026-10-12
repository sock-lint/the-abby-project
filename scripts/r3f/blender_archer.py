"""Private Blender worker for the publisher's existing modular Archer art."""
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector


def reset():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)


def import_fbx(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.fbx(filepath=str(path), use_anim=False)
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
    result.blend_method = 'CLIP'
    result.alpha_threshold = 0.5
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
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 512
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
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


def main():
    config = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf-8'))
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
