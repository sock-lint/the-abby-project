"""Synthetic Blender rig checks; run with Blender's Python or official bpy.

These validate conversion math and rejection behavior, not purchased-art fit.
No publisher files are needed or accepted by this test module.

blender --background --factory-startup --python scripts/r3f/test_blender_archer.py
"""
import importlib.util
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest

try:
    import bpy
    from mathutils import Matrix, Quaternion, Vector
except ModuleNotFoundError:
    bpy = None

worker = None
if bpy is not None:
    spec = importlib.util.spec_from_file_location('blender_archer', Path(__file__).with_name('blender_archer.py'))
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)


@unittest.skipIf(bpy is None, 'Optional Blender/bpy is unavailable; no purchased-art evidence is claimed')
class SuppliedRestBasisTests(unittest.TestCase):
    def setUp(self):
        worker.reset()

    def test_review_crown_keeps_each_saved_hairstyle_and_only_hood_uses_hat_hair(self):
        names = ['Archer_Hair_01', 'Archer_Hair_02', 'Archer_Hair_03', 'Archer_Hair_04', 'Archer_Hair_For_Hat']
        data = bpy.data.meshes.new('Synthetic review hair')
        meshes = {name: bpy.data.objects.new(name, data) for name in names}
        for obj in meshes.values():
            bpy.context.collection.objects.link(obj)
        for hairstyle in names[:4]:
            for headwear, expected in (('none', {hairstyle}), ('crown-eve', {hairstyle}), ('hood-mystical', {'Archer_Hair_For_Hat'})):
                with self.subTest(headwear=headwear, hairstyle=hairstyle):
                    for name, mesh in meshes.items():
                        mesh.hide_render = worker.review_hair_hidden(name, headwear, hairstyle)
                    self.assertEqual({name for name, mesh in meshes.items() if not mesh.hide_render}, expected)

    def rig(self, name, roll=0, child_name='Head'):
        data = bpy.data.armatures.new(name)
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        root = data.edit_bones.new('Root')
        root.head, root.tail, root.roll = (0, 0, 0), (0, 0, 1), roll
        head = data.edit_bones.new(child_name)
        head.head, head.tail, head.roll = (0, 0, 1), (0, 0, 1.5), roll
        head.parent = root
        bpy.ops.object.mode_set(mode='OBJECT')
        obj.select_set(False)
        return obj

    def moving_source(self, child_name='Head'):
        source = self.rig('Synthetic supplied rig', child_name=child_name)
        head = source.pose.bones[child_name]
        head.rotation_mode = 'QUATERNION'
        for frame, angle in ((1, 0), (2, 0.2), (3, 0.4)):
            head.rotation_quaternion = Quaternion((1, 0, 0), angle)
            head.keyframe_insert(data_path='rotation_quaternion', frame=frame)
        return source

    def test_pose_delta_conversion_preserves_motion_when_direct_track_copy_distorts_it(self):
        source = self.moving_source()
        target = self.rig('Synthetic costume rig', roll=math.pi / 2)
        point = Vector((0.2, 0.1, 1.3))
        source_rest = source.matrix_world @ source.data.bones['Head'].matrix_local
        target_rest = target.matrix_world @ target.data.bones['Head'].matrix_local
        target.animation_data_create().action = source.animation_data.action
        worker.at_frame(3)
        expected = source.matrix_world @ source.pose.bones['Head'].matrix @ source_rest.inverted() @ point
        blindly_copied = target.matrix_world @ target.pose.bones['Head'].matrix @ target_rest.inverted() @ point
        self.assertGreater((blindly_copied - expected).length, 0.05)
        target.animation_data.action = None
        measurements, deltas = worker.convert_supplied_motion(source, target, [1, 2, 3])
        self.assertLess(measurements['target_joint_error'], 0.0001)
        self.assertLess(measurements['rotation_delta_error'], 0.0001)
        for frame in (1, 2, 3):
            worker.at_frame(frame)
            actual = target.matrix_world @ target.pose.bones['Head'].matrix @ target_rest.inverted() @ point
            self.assertLess((actual - deltas[frame]['Head'] @ point).length, 0.00001)

    def test_different_proportions_keep_target_bone_lengths_and_supplied_rotations(self):
        source = self.moving_source()
        target = self.rig('Shorter costume rig', roll=math.pi / 2)
        target.location.x = 0.01
        bpy.context.view_layer.objects.active = target
        target.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        target.data.edit_bones['Root'].tail = (0, 0, 0.6)
        target.data.edit_bones['Head'].head = (0, 0, 0.6)
        target.data.edit_bones['Head'].tail = (0, 0, 0.9)
        bpy.ops.object.mode_set(mode='OBJECT')
        target.select_set(False)
        bpy.context.view_layer.update()
        original = {bone.name: bone.matrix_local.copy() for bone in target.data.bones}
        measurements, _ = worker.convert_supplied_motion(source, target, [1, 2, 3])
        self.assertGreater(measurements['source_rest_joint_difference'], 0.3)
        self.assertLess(measurements['target_joint_error'], 0.00001)
        self.assertLess(measurements['rotation_delta_error'], 0.00001)
        for frame in (1, 2, 3):
            worker.at_frame(frame)
            root = target.pose.bones['Root'].matrix.translation
            head = target.pose.bones['Head'].matrix.translation
            self.assertAlmostEqual((head - root).length, 0.6, places=5)
        for bone in target.data.bones:
            self.assertEqual(bone.matrix_local, original[bone.name])

    def test_supplied_root_translation_is_preserved_without_copying_source_child_offsets(self):
        source = self.moving_source()
        for frame, value in ((1, 0), (2, 0.1), (3, 0.2)):
            source.pose.bones['Root'].location.x = value
            source.pose.bones['Root'].keyframe_insert(data_path='location', frame=frame)
        target = self.rig('Translated costume', roll=math.pi / 2)
        target.location.x = 0.4
        bpy.context.view_layer.update()
        worker.convert_supplied_motion(source, target, [1, 2, 3])
        worker.at_frame(3)
        self.assertAlmostEqual((target.matrix_world @ target.pose.bones['Root'].matrix).translation.x, 0.6, places=5)

    def test_dynamic_nonroot_translation_is_rejected_before_animation_is_baked(self):
        source = self.moving_source()
        for frame, value in ((1, 0), (2, 0.1), (3, 0)):
            source.pose.bones['Head'].location.x = value
            source.pose.bones['Head'].keyframe_insert(data_path='location', frame=frame)
        target = self.rig('Untouched costume')
        with self.assertRaisesRegex(ValueError, 'nonroot joint translations'):
            worker.convert_supplied_motion(source, target, [1, 2, 3])
        self.assertIsNone(target.animation_data)

    def test_dynamic_uniform_scale_is_rejected_before_animation_is_baked(self):
        source = self.moving_source()
        for frame, value in ((1, 1), (2, 1.1), (3, 1)):
            source.pose.bones['Head'].scale = (value,) * 3
            source.pose.bones['Head'].keyframe_insert(data_path='scale', frame=frame)
        target = self.rig('Untouched costume')
        with self.assertRaisesRegex(ValueError, 'rig scale'):
            worker.convert_supplied_motion(source, target, [1, 2, 3])
        self.assertIsNone(target.animation_data)

    def test_hierarchy_and_scale_mismatches_are_rejected(self):
        source = self.moving_source()
        target = self.rig('Wrong hierarchy')
        bpy.context.view_layer.objects.active = target
        target.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        target.data.edit_bones['Head'].parent = None
        bpy.ops.object.mode_set(mode='OBJECT')
        with self.assertRaisesRegex(ValueError, 'topology'):
            worker.matching_rest_rigs(source, target)
        target = self.rig('Wrong scale')
        target.scale = (2, 2, 2)
        bpy.context.view_layer.update()
        with self.assertRaisesRegex(ValueError, 'scales'):
            worker.matching_rest_rigs(source, target)

    def test_shear_and_reflection_are_rejected(self):
        shear = Matrix.Identity(4)
        shear[0][1] = 0.1
        for matrix in (shear, Matrix.Diagonal((-1, 1, 1, 1))):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                worker.rigid_scale(matrix)

    def test_extra_nonbone_animation_track_cannot_be_silently_dropped(self):
        source = self.moving_source()
        source.location.x = 0.1
        source.keyframe_insert(data_path='location', frame=1)
        with self.assertRaisesRegex(ValueError, 'unhandled animation tracks'):
            worker.supplied_idle([source])

    def test_only_constant_unreferenced_empty_transform_actions_can_be_ignored(self):
        source = self.moving_source()
        helper = bpy.data.objects.new('Synthetic FBX export helper', None)
        bpy.context.collection.objects.link(helper)
        for frame in (1, 3):
            helper.location.x = 2
            helper.keyframe_insert(data_path='location', frame=frame)
        rig, _, _ = worker.supplied_idle([source, helper])
        self.assertEqual(rig, source)
        helper.location.x = 3
        helper.keyframe_insert(data_path='location', frame=2)
        with self.assertRaisesRegex(ValueError, 'extra animated objects'):
            worker.supplied_idle([source, helper])

    def test_constant_empty_transform_is_rejected_if_another_source_object_references_it(self):
        source = self.moving_source()
        helper = bpy.data.objects.new('Synthetic referenced helper', None)
        bpy.context.collection.objects.link(helper)
        for frame in (1, 3):
            helper.keyframe_insert(data_path='location', frame=frame)
        source.parent = helper
        with self.assertRaisesRegex(ValueError, 'extra animated objects'):
            worker.supplied_idle([source, helper])

    def test_head_attachment_keeps_rest_mesh_and_then_follows_supplied_head_motion(self):
        source = self.moving_source()
        target = self.rig('Synthetic costume rig', roll=math.pi / 2)
        data = bpy.data.meshes.new('Synthetic hair geometry')
        data.from_pydata([(0.2, 0.1, 1.3), (0.3, 0.1, 1.3), (0.2, 0.2, 1.3)], [], [(0, 1, 2)])
        data.uv_layers.new()
        mesh = bpy.data.objects.new('Synthetic hair module', data)
        bpy.context.collection.objects.link(mesh)
        rest = worker.attach_head_module(mesh, target, 'Head')
        _, deltas = worker.convert_supplied_motion(source, target, [1, 2, 3])
        worker.at_frame(3)
        predicted = [deltas[3]['Head'] @ point for point in rest]
        self.assertLess(worker.vertex_error(predicted, worker.vertices(mesh)), 0.00001)
        self.assertGreater(worker.vertex_error(rest, worker.vertices(mesh)), 0.05)

    def test_reimport_comparison_handles_uv_seam_splits_and_rejects_distortion(self):
        original = [Vector((0, 0, 0)), Vector((1, 0, 0)), Vector((0, 1, 0))]
        split = [original[2], original[0], original[1], original[0]]
        self.assertEqual(worker.surface_error(original, split), 0)
        split[0] = Vector((0, 1.1, 0))
        self.assertGreater(worker.surface_error(original, split), 0.09)

    def test_prefab_attachment_keeps_geometry_uvs_and_follows_its_selected_joint(self):
        source = self.moving_source(child_name='RigLPalm')
        target = self.rig('Synthetic wardrobe costume', roll=math.pi / 2, child_name='RigLPalm')
        data = bpy.data.meshes.new('Synthetic accessory geometry')
        data.from_pydata([(0.2, 1.3, 0.1), (0.3, 1.3, 0.1), (0.2, 1.3, 0.2)], [], [(0, 1, 2)])
        data.uv_layers.new()
        mesh = bpy.data.objects.new('Synthetic accessory', data)
        bpy.context.collection.objects.link(mesh)
        geometry = [vertex.co.copy() for vertex in data.vertices]
        uvs = worker.uv_values(mesh)
        socket = Matrix.Translation((0.2, -0.1, 0)) @ Matrix.Rotation(0.3, 4, 'Z')
        attachment = {'bone': 'RigLPalm', 'bone_position': [0, 0, 1], 'world_matrix': [list(row) for row in socket]}
        palm = target.pose.bones['RigLPalm']
        palm.rotation_mode = 'QUATERNION'
        palm.rotation_quaternion = Quaternion((1, 0, 0), 0.1)
        palm.location = (0.0000037, -0.0000086, -0.00000075)
        bpy.context.view_layer.update()
        original_pose = palm.matrix_basis.copy()
        original_mode = target.data.pose_position
        expected_rest = [socket @ Matrix.Rotation(math.pi / 2, 4, 'X') @ mesh.matrix_world @ point for point in geometry]
        rest = worker.attach_wardrobe_module(mesh, target, attachment)
        self.assertEqual(palm.matrix_basis, original_pose)
        self.assertEqual(target.data.pose_position, original_mode)
        self.assertLess(worker.vertex_error(expected_rest, rest), 0.000001)
        target.data.pose_position = 'REST'
        bpy.context.view_layer.update()
        self.assertLess(worker.vertex_error(expected_rest, worker.vertices(mesh)), 0.000001)
        target.data.pose_position = original_mode
        bpy.context.view_layer.update()
        self.assertGreater(worker.vertex_error(rest, worker.vertices(mesh)), 0.01)
        for point, actual in zip(geometry, data.vertices):
            self.assertEqual(point, actual.co)
        self.assertEqual(uvs, worker.uv_values(mesh))
        self.assertTrue(all(vertex.groups[0].weight == 1 for vertex in data.vertices))
        _, deltas = worker.convert_supplied_motion(source, target, [1, 2, 3])
        worker.at_frame(3)
        self.assertLess(worker.vertex_error([deltas[3]['RigLPalm'] @ point for point in rest], worker.vertices(mesh)), 0.00001)
        self.assertGreater(worker.vertex_error(rest, worker.vertices(mesh)), 0.05)

    def test_wrong_prefab_joint_and_nonrigid_socket_are_rejected_before_attachment(self):
        rig = self.rig('Synthetic wardrobe rig')
        data = bpy.data.meshes.new('Synthetic accessory geometry')
        data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        mesh = bpy.data.objects.new('Synthetic accessory', data)
        bpy.context.collection.objects.link(mesh)
        attachment = {'bone': 'Head', 'bone_position': [0.2, 0, 1], 'world_matrix': [list(row) for row in Matrix.Identity(4)]}
        with self.assertRaisesRegex(ValueError, 'prefab joint'):
            worker.attach_wardrobe_module(mesh, rig, attachment)
        attachment['bone_position'] = [0, 0, 1]
        attachment['world_matrix'][0][1] = 0.2
        with self.assertRaises(ValueError):
            worker.attach_wardrobe_module(mesh, rig, attachment)
        self.assertEqual(len(mesh.vertex_groups), 0)
        self.assertEqual(len(mesh.modifiers), 0)

    def test_surface_check_excludes_only_unused_points_and_still_rejects_visible_distortion(self):
        data = bpy.data.meshes.new('Synthetic triangle with unused position')
        data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0), (10, 10, 10)], [], [(0, 1, 2)])
        mesh = bpy.data.objects.new('Synthetic triangle with unused position', data)
        bpy.context.collection.objects.link(mesh)
        source = worker.vertices(mesh, surface_only=True)
        self.assertEqual(len(source), 3)
        self.assertEqual(len(mesh.data.vertices), 4)
        data.vertices[3].co = (20, 20, 20)
        data.update()
        bpy.context.view_layer.update()
        # A non-face point changes no rendered surface and stays in source data.
        self.assertEqual(worker.surface_error(source, worker.vertices(mesh, surface_only=True)), 0)
        data.vertices[1].co.x += 0.05
        data.update()
        bpy.context.view_layer.update()
        self.assertGreater(worker.surface_error(source, worker.vertices(mesh, surface_only=True)), 0.001)

    def test_hidden_importer_bone_shape_is_removed_before_next_export(self):
        data = bpy.data.meshes.new('Synthetic hidden bone shape')
        obj = bpy.data.objects.new('Synthetic hidden bone shape', data)
        bpy.context.collection.objects.link(obj)
        obj.hide_set(True)
        worker.reset()
        self.assertNotIn('Synthetic hidden bone shape', bpy.data.objects)

    def test_export_retains_fifth_weight_and_reimports_its_original_deformation(self):
        rig = self.rig('Synthetic five-weight rig')
        bpy.context.view_layer.objects.active = rig
        rig.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        for index in range(3):
            bone = rig.data.edit_bones.new(f'Extra{index}')
            bone.head, bone.tail = (0, 0, 0.2 * index), (0.1, 0, 0.2 * index + 0.2)
            bone.parent = rig.data.edit_bones['Root']
        bpy.ops.object.mode_set(mode='OBJECT')
        mesh_data = bpy.data.meshes.new('Synthetic weighted triangle')
        mesh_data.from_pydata([(0.2, 0.1, 1.3), (0.3, 0.1, 1.3), (0.2, 0.2, 1.3)], [], [(0, 1, 2)])
        mesh_data.uv_layers.new()
        mesh = bpy.data.objects.new('Synthetic weighted triangle', mesh_data)
        bpy.context.collection.objects.link(mesh)
        mesh.parent = rig
        for bone in rig.data.bones:
            group = mesh.vertex_groups.new(name=bone.name)
            group.add([0, 1, 2], 0.2, 'REPLACE')
        modifier = mesh.modifiers.new('Supplied synthetic weights', 'ARMATURE')
        modifier.object = rig
        for frame, angle in ((1, 0), (2, 0.4), (3, 0)):
            rig.pose.bones['Extra2'].rotation_mode = 'QUATERNION'
            rig.pose.bones['Extra2'].rotation_quaternion = Quaternion((0, 0, 1), angle)
            rig.pose.bones['Extra2'].keyframe_insert(data_path='rotation_quaternion', frame=frame)
        rig.animation_data.action.name = 'SyntheticIdle'
        worker.at_frame(2)
        expected = worker.vertices(mesh)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.glb'
            worker.export_modular(path)
            data = path.read_bytes()
            length = struct.unpack_from('<I', data, 12)[0]
            document = json.loads(data[20:20 + length])
            attributes = document['meshes'][0]['primitives'][0]['attributes']
            self.assertIn('JOINTS_1', attributes)
            self.assertIn('WEIGHTS_1', attributes)
            duration = 2 / (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base)
            for sampler in document['animations'][0]['samplers']:
                time = document['accessors'][sampler['input']]
                self.assertEqual(time['min'], [0])
                self.assertAlmostEqual(time['max'][0], duration, places=6)
            worker.reset()
            bpy.ops.import_scene.gltf(filepath=str(path))
            runtime = next(obj for obj in bpy.context.scene.objects if obj.type == 'MESH' and obj.name == 'Synthetic weighted triangle')
            action = runtime.find_armature().animation_data.action
            start, end = action.frame_range
            worker.at_frame((start + end) / 2)
            self.assertLess(worker.surface_error(expected, worker.vertices(runtime)), 0.00001)


if __name__ == '__main__':
    # Blender's own flags are not unittest flags.
    unittest.main(argv=[__file__])
