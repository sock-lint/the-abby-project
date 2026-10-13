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
