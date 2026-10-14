"""Fail-closed Archer source/evidence checks using synthetic private inputs."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location('prepare_archer', Path(__file__).with_name('prepare_archer.py'))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class ReviewedSourceMapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / 'owned'
        self.source.mkdir()
        for filename in ('body.fbx', 'head.fbx', 'face.fbx', 'hair.fbx', 'idle.fbx', 'palette.png', 'hair.mat'):
            (self.source / filename).write_text('synthetic input', encoding='utf-8')
        self.config = {
            'schema_version': 2, 'source_review_reference': 'synthetic inventory review',
            'bodies': {style: 'body.fbx' for style in prepare.OUTFIT_STYLES},
            'head': {style: 'head.fbx' for style in prepare.HEAD_STYLES}, 'face': 'face.fbx',
            'hair': {style: 'hair.fbx' for style in prepare.HAIR_STYLES},
            'idle': 'idle.fbx', 'head_bone': 'SyntheticHead',
            'textures': {
                'outfit': {key: {'source': 'palette.png'} for key in prepare.OUTFIT_KEYS},
                'hair': {key: {'source': 'palette.png', 'material': 'hair.mat'} for key in prepare.HAIR_COLORS},
                'face': {key: {'source': 'palette.png'} for key in prepare.FACE_KEYS},
            },
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_explicit_shared_palette_is_accepted_without_inventing_extra_names(self):
        checked = prepare.reviewed_source_map(self.source, self.config)
        self.assertEqual(checked['textures']['face']['face-03:brown']['source'], 'palette.png')
        self.assertEqual(len(checked['textures']['outfit']), 24)
        self.assertEqual(prepare.source_map_files(checked), ('body.fbx', 'face.fbx', 'hair.fbx', 'hair.mat', 'head.fbx', 'idle.fbx', 'palette.png'))

    def test_incomplete_faces_or_costume_palettes_are_rejected(self):
        for group, key in (('face', 'face-02:grey'), ('hair', 'brown'), ('outfit', 'archer-03:tan:fire')):
            with self.subTest(group=group):
                config = deepcopy(self.config)
                del config['textures'][group][key]
                with self.assertRaisesRegex(ValueError, 'reviewed choices'):
                    prepare.reviewed_source_map(self.source, config)

    def test_missing_review_or_head_identity_is_rejected(self):
        for key in ('source_review_reference', 'head_bone'):
            with self.subTest(key=key):
                config = deepcopy(self.config)
                config[key] = ''
                with self.assertRaisesRegex(ValueError, 'reviewed'):
                    prepare.reviewed_source_map(self.source, config)

    def test_unknown_palette_source_and_script_inputs_are_rejected(self):
        config = deepcopy(self.config)
        config['textures']['face']['face-01:brown'] = {'source': 'unverified-brown.png'}
        with self.assertRaisesRegex(FileNotFoundError, 'Reviewed Archer source is missing'):
            prepare.reviewed_source_map(self.source, config)
        config['textures']['face']['face-01:brown'] = {'source': 'publisher-demo.py'}
        with self.assertRaisesRegex(ValueError, 'required type'):
            prepare.reviewed_source_map(self.source, config)

    def test_source_traversal_and_external_symlinks_are_rejected(self):
        outside = self.root / 'outside.png'
        outside.write_text('synthetic outside input', encoding='utf-8')
        (self.source / 'linked.png').symlink_to(outside)
        for path in ('../outside.png', str(outside), 'linked.png', r'..\outside.png'):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'relative pack|escapes'):
                prepare.source_file(self.source, path, ('.png',))

    def test_source_material_tint_is_read_without_assuming_hair_palette_pixels(self):
        path = self.source / 'hair.mat'
        path.write_text('- _BaseColor: {r: 0.25, g: 0.5, b: 0.75, a: 1}', encoding='utf-8')
        self.assertEqual(prepare.publisher_color(path), (0.25, 0.5, 0.75, 1))

    def test_original_standard_tint_and_converted_urp_tint_are_both_supported(self):
        path = self.source / 'hair.mat'
        path.write_text('- _Color: {r: 0.8, g: 0.4, b: 0, a: 1}', encoding='utf-8')
        self.assertEqual(prepare.publisher_color(path), (0.8, 0.4, 0, 1))
        path.write_text(path.read_text() + '\n- _BaseColor: {r: 0.25, g: 0.5, b: 0.75, a: 1}', encoding='utf-8')
        self.assertEqual(prepare.publisher_color(path), (0.25, 0.5, 0.75, 1))

    def test_partial_repository_exports_are_staged_only_in_an_ignored_directory(self):
        output = prepare.ROOT / 'frontend/src/avatar/licensed'
        staging = prepare.private_staging_parent(output, self.source)
        self.assertEqual(staging, prepare.ROOT / 'scripts/r3f/private')
        self.assertNotEqual(staging, output.parent)
        prepare.ensure_private_output(staging / '.archer-synthetic-partial', self.source)

    def test_refused_conversion_preserves_existing_private_export(self):
        output = self.root / 'existing-private-export'
        output.mkdir()
        previous = output / 'manifest.json'
        previous.write_text('preserve prior reviewed release', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Preserve the existing private avatar export'):
            prepare.prepare_modular(self.source, output, Path('unexecuted-blender'), self.config)
        self.assertEqual(previous.read_text(), 'preserve prior reviewed release')
        self.assertEqual(list(output.iterdir()), [previous])


class WardrobeSourceMapTests(unittest.TestCase):
    def setUp(self):
        ReviewedSourceMapTests.setUp(self)
        self.config['schema_version'] = 3
        self.config['head_bone'] = 'RigHead'
        self.groups = {'headwear': ('crown-eve', 'hood-mystical'), 'mask': ('mask-undercover',), 'bow': ('bow-greenhorn', 'bow-vines', 'bow-myth'), 'quiver': ('quiver-angel', 'quiver-rook', 'quiver-tale')}
        self.sockets = {'head': ('+ Head', 'RigHead'), 'left_hand': ('+ L Hand', 'RigLPalm'), 'back': ('+ Back', 'RigRibcage')}
        (self.source / 'equipment.fbx').write_text('synthetic equipment')
        metadata = self.source / 'Unity Metadata'
        metadata.mkdir()
        for name, number in (('equipment.fbx', 1), ('body.fbx', 2), ('palette.mat', 3), ('palette.png', 4)):
            (metadata / (name + '.meta')).write_text(f'guid: {number:032x}\n')
        (self.source / 'palette.mat').write_text(f'm_Name: Synthetic Palette\n- _MainTex:\n    m_Texture: {{fileID: 1, guid: {4:032x}, type: 3}}\n')
        (self.source / 'equipment.prefab').write_text(f'--- !u!33 &1\nMeshFilter:\n  m_Mesh: {{fileID: 1, guid: {1:032x}, type: 3}}\n--- !u!23 &2\nMeshRenderer:\n  m_Materials:\n  - {{fileID: 1, guid: {3:032x}, type: 2}}\n')
        nodes = [('Root', 0, (0, 0, 0)), ('RigHead', 1, (0, 1, 0)), ('RigLPalm', 1, (0.5, 0.5, 0)), ('RigRibcage', 1, (0, 0.6, 0)), ('+ Head', 2, (0, -1, 0)), ('+ L Hand', 3, (0.1, 0, 0)), ('+ Back', 4, (0, 0, -0.1))]
        body = f'--- !u!137 &99\nSkinnedMeshRenderer:\n  m_Mesh: {{fileID: 1, guid: {2:032x}, type: 3}}\n'
        for index, (name, parent, position) in enumerate(nodes, 1):
            body += f'--- !u!1 &{index}\nGameObject:\n  m_Name: {name}\n--- !u!4 &{index + 10}\nTransform:\n  m_GameObject: {{fileID: {index}}}\n  m_Father: {{fileID: {parent + 10 if parent else 0}}}\n  m_LocalPosition: {{x: {position[0]}, y: {position[1]}, z: {position[2]}}}\n  m_LocalRotation: {{x: 0, y: 0, z: 0, w: 1}}\n  m_LocalScale: {{x: 1, y: 1, z: 1}}\n'
        (self.source / 'body.prefab').write_text(body)
        wardrobe = {'hair_for_hat': {'source': 'equipment.fbx', 'prefab': 'equipment.prefab', 'attachment': 'head'}}
        for group, styles in self.groups.items():
            socket = 'left_hand' if group == 'bow' else 'back' if group == 'quiver' else 'head'
            wardrobe[group] = {style: {'source': 'equipment.fbx', 'prefab': 'equipment.prefab', 'attachment': socket} for style in styles}
        wardrobe['attachments'] = {style: {key: {'prefab': 'body.prefab', 'point': point, 'bone': bone} for key, (point, bone) in self.sockets.items()} for style in prepare.OUTFIT_STYLES}
        self.config['wardrobe'] = wardrobe
        self.config['textures']['wardrobe'] = {f'{style}:{palette}': {'source': 'palette.png', 'material': 'palette.mat', 'prefab': 'equipment.prefab'} for styles in self.groups.values() for style in styles for palette in ('aqua', 'nature', 'fire', 'dark')}
        for descriptor in self.config['textures']['hair'].values():
            descriptor['material'] = 'palette.mat'

    def tearDown(self):
        self.temporary.cleanup()

    def test_wardrobe_uses_actual_prefab_sockets_and_all_four_supplied_palettes(self):
        checked = prepare.reviewed_source_map(self.source, self.config)
        attachments = prepare.wardrobe_attachments(self.source, checked)
        self.assertEqual(len(checked['textures']['wardrobe']), 36)
        self.assertAlmostEqual(attachments['archer-01']['left_hand']['world_matrix'][0][3], -0.6)
        self.assertAlmostEqual(attachments['archer-01']['left_hand']['world_matrix'][2][3], 0.5)
        self.assertAlmostEqual(attachments['archer-01']['back']['world_matrix'][1][3], 0.1)
        self.assertEqual(attachments['archer-01']['head']['bone'], 'RigHead')
        self.assertIn('body.prefab', prepare.source_map_files(checked))
        self.assertIn('Unity Metadata/equipment.fbx.meta', prepare.source_map_files(checked))

    def test_missing_wardrobe_choice_or_palette_is_rejected(self):
        for group, key in (('bow', 'bow-myth'), ('headwear', 'hood-mystical')):
            config = deepcopy(self.config)
            del config['wardrobe'][group][key]
            with self.subTest(group=group), self.assertRaisesRegex(ValueError, 'reviewed choices'):
                prepare.reviewed_source_map(self.source, config)
        del self.config['textures']['wardrobe']['crown-eve:dark']
        with self.assertRaisesRegex(ValueError, 'reviewed choices'):
            prepare.reviewed_source_map(self.source, self.config)

    def test_wrong_socket_parent_or_module_attachment_is_rejected(self):
        self.config['wardrobe']['attachments']['archer-01']['head']['bone'] = 'RigLPalm'
        with self.assertRaisesRegex(ValueError, 'parent bone'):
            prepare.reviewed_source_map(self.source, self.config)
        self.config['wardrobe']['attachments']['archer-01']['head']['bone'] = 'RigHead'
        self.config['wardrobe']['bow']['bow-myth']['attachment'] = 'head'
        with self.assertRaisesRegex(ValueError, 'attachment'):
            prepare.reviewed_source_map(self.source, self.config)

    def test_prefab_mesh_and_material_guids_must_match_the_actual_sources(self):
        path = self.source / 'equipment.prefab'
        original = path.read_text()
        for number in (1, 3):
            path.write_text(original.replace(f'{number:032x}', f'{9:032x}'))
            with self.subTest(number=number), self.assertRaisesRegex(ValueError, 'GUID'):
                prepare.reviewed_source_map(self.source, self.config)
        path.write_text(original)

    def test_prefab_external_paths_nonfinite_transforms_and_cycles_are_rejected(self):
        config = deepcopy(self.config)
        config['wardrobe']['hair_for_hat']['prefab'] = '../outside.prefab'
        with self.assertRaisesRegex(ValueError, 'relative pack'):
            prepare.reviewed_source_map(self.source, config)
        path = self.source / 'body.prefab'
        original = path.read_text()
        for mutated in (original.replace('m_LocalPosition: {x: 0,', 'm_LocalPosition: {x: NaN,', 1), original.replace('m_Father: {fileID: 0}', 'm_Father: {fileID: 15}', 1)):
            path.write_text(mutated)
            with self.subTest(mutated=mutated[:30]), self.assertRaises(ValueError):
                prepare.reviewed_source_map(self.source, self.config)


class SuppliedAnimationEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            'method': 'supplied-hierarchy-rotation-retarget-v1', 'duration_seconds': 2.0,
            'sampled_frames': 61, 'moving_vertices': 200,
            'source_rest_joint_difference': 0.15, 'target_joint_error': 0.000001,
            'rotation_delta_error': 0.000001, 'nonroot_translation_variation': 0.000001,
            'source_scale_variation': 0.000001, 'head_attachment_error': 0.000001,
            'reimport_max_vertex_error': 0.00001,
        }

    def test_only_measured_conversion_report_is_accepted(self):
        self.assertEqual(prepare.animation_validation(self.report), self.report)
        self.assertNotIn('animation_review_reference', self.report)

    def test_missing_motion_and_incompatible_deformation_remain_blocked(self):
        for key, value in (('duration_seconds', 0), ('moving_vertices', 0), ('sampled_frames', 2), ('source_rest_joint_difference', -1), ('target_joint_error', 0.01), ('rotation_delta_error', 0.01), ('nonroot_translation_variation', 0.01), ('source_scale_variation', 0.01), ('head_attachment_error', 0.01), ('reimport_max_vertex_error', 0.01)):
            with self.subTest(key=key):
                report = {**self.report, key: value}
                with self.assertRaises(ValueError):
                    prepare.animation_validation(report)

    def test_nonfinite_and_boolean_evidence_cannot_pass_review(self):
        for key in ('duration_seconds', 'sampled_frames', 'moving_vertices', 'source_rest_joint_difference', 'target_joint_error', 'rotation_delta_error', 'nonroot_translation_variation', 'source_scale_variation', 'head_attachment_error', 'reimport_max_vertex_error'):
            for value in (True, float('nan'), float('inf'), 'verified'):
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, 'finite measurements'):
                    prepare.animation_validation({**self.report, key: value})

    def test_fake_owner_approval_is_not_conversion_evidence(self):
        with self.assertRaisesRegex(ValueError, 'reviewed choices'):
            prepare.animation_validation({**self.report, 'owner_accepted': True})

    def test_fractional_sample_and_vertex_counts_are_rejected(self):
        for key in ('sampled_frames', 'moving_vertices'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'integers'):
                prepare.animation_validation({**self.report, key: 3.5})


if __name__ == '__main__':
    unittest.main()
