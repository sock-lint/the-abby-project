#!/usr/bin/env python
"""Convert owned modular Archer sources for private avatar review.

No original inputs are modified, no new clothing is fitted and no skeletal
animation is authored. The selected publisher body/head/face/hair geometry and
palette textures form a static avatar. Original Idle remains unaccepted because
its bind matrices differ from the body rig; it is never silently retargeted.

An explicitly reviewed source map enables the three-costume conversion path.
That path validates supplied Idle motion against each costume's own rest rig,
and leaves animation and public-delivery acceptance to a separate owner review.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from prepare_meshtint import ROOT, LICENSE_URL, ensure_private_output, find_blender, sha256, verify_export

BODY_PALETTES = [(skin, outfit) for skin in ('fair', 'tan') for outfit in ('aqua', 'nature', 'fire', 'dark')]
HAIR_VARIANTS = {'dark': ('Hair Dark', 'Hair Black'), 'light': ('Hair Light', 'Hair Blonde')}
OUTFIT_STYLES = ('archer-01', 'archer-02', 'archer-03')
HAIR_COLORS = ('dark', 'light', 'brown', 'orange', 'grey')
HAIR_STYLES = tuple(f'hair-{index:02}' for index in range(1, 5))
FACE_STYLES = ('face-01', 'face-02', 'face-03')
FACE_KEYS = tuple(f'{style}:{color}' for style in FACE_STYLES for color in HAIR_COLORS)
HEAD_STYLES = ('head-01', 'head-02')
OUTFIT_KEYS = tuple(f'{style}:{skin}:{palette}' for style in OUTFIT_STYLES for skin, palette in BODY_PALETTES)
WARDROBE_STYLES = {'headwear': ('crown-eve', 'hood-mystical'), 'mask': ('mask-undercover',), 'bow': ('bow-greenhorn', 'bow-vines', 'bow-myth'), 'quiver': ('quiver-angel', 'quiver-rook', 'quiver-tale')}
WARDROBE_KEYS = tuple(f'{style}:{palette}' for styles in WARDROBE_STYLES.values() for style in styles for palette in ('aqua', 'nature', 'fire', 'dark'))
WARDROBE_SOCKETS = {'head': ('+ Head', 'RigHead'), 'left_hand': ('+ L Hand', 'RigLPalm'), 'back': ('+ Back', 'RigRibcage')}


def wardrobe_parts() -> dict:
    return {'hair_for_hat': 'Archer_Hair_For_Hat', **{group: {style: 'Archer_' + style.replace('-', '_').title() for style in styles} for group, styles in WARDROBE_STYLES.items()}}


def exact_keys(value: object, keys: tuple[str, ...], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f'{label} must declare exactly the reviewed choices')
    return value


def source_file(source: Path, relative: object, suffixes: tuple[str, ...]) -> Path:
    """Resolve only an existing pack file; never follow an external symlink."""
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('Source paths must be relative pack paths')
    path = Path(relative)
    if path.is_absolute() or '..' in path.parts or path.suffix.lower() not in suffixes:
        raise ValueError('Source paths must be relative pack paths with the required type')
    resolved = (source / path).resolve()
    if not resolved.is_relative_to(source.resolve()):
        raise ValueError('Source path escapes the owned pack')
    if not resolved.is_file():
        raise FileNotFoundError(f'Reviewed Archer source is missing: {relative}')
    return resolved


def reviewed_source_map(source: Path, config: object) -> dict:
    """Validate explicit inventory rather than inventing extra palette names.

    The private source map names actual publisher textures/materials for each
    choice. Repeated texture descriptors explicitly share those source pixels;
    no source filename, UV layout or face-color compatibility is inferred.
    """
    if not isinstance(config, dict) or config.get('schema_version') not in (2, 3):
        raise ValueError('Modular source map must use schema version 2 or 3')
    expanded = config['schema_version'] == 3
    keys = ('schema_version', 'source_review_reference', 'bodies', 'head', 'face', 'hair', 'idle', 'head_bone', 'textures')
    exact_keys(config, (*keys, 'wardrobe') if expanded else keys, 'Source map')
    for key in ('source_review_reference', 'head_bone'):
        if not isinstance(config[key], str) or not config[key].strip() or len(config[key]) > 512:
            raise ValueError(f'Source map needs a reviewed {key}')
    bodies = exact_keys(config['bodies'], OUTFIT_STYLES, 'Body sources')
    heads = exact_keys(config['head'], HEAD_STYLES, 'Head sources')
    hair = exact_keys(config['hair'], HAIR_STYLES, 'Hair sources')
    for path in [*bodies.values(), *heads.values(), *hair.values(), config['face'], config['idle']]:
        source_file(source, path, ('.fbx',))
    textures = exact_keys(config['textures'], ('outfit', 'hair', 'face', 'wardrobe') if expanded else ('outfit', 'hair', 'face'), 'Textures')
    groups = [('outfit', OUTFIT_KEYS), ('hair', HAIR_COLORS), ('face', FACE_KEYS)]
    if expanded:
        groups.append(('wardrobe', WARDROBE_KEYS))
    for group, keys in groups:
        choices = exact_keys(textures[group], keys, f'{group} textures')
        for descriptor in choices.values():
            allowed = ({'source', 'material', 'prefab'},) if group == 'wardrobe' else ({'source'}, {'source', 'material'})
            if not isinstance(descriptor, dict) or set(descriptor) not in allowed:
                raise ValueError('Each texture needs its actual source and optional publisher material')
            source_file(source, descriptor['source'], ('.psd', '.png'))
            if 'material' in descriptor:
                source_file(source, descriptor['material'], ('.mat',))
    if expanded:
        wardrobe = exact_keys(config['wardrobe'], ('hair_for_hat', *WARDROBE_STYLES, 'attachments'), 'Wardrobe sources')
        for group, styles in WARDROBE_STYLES.items():
            exact_keys(wardrobe[group], styles, f'{group} sources')
        for group, style, descriptor in wardrobe_modules(config):
            exact_keys(descriptor, ('source', 'prefab', 'attachment'), 'Wardrobe module')
            socket = 'left_hand' if group == 'bow' else 'back' if group == 'quiver' else 'head'
            if descriptor['attachment'] != socket:
                raise ValueError('Wardrobe module uses the wrong publisher attachment')
            source_file(source, descriptor['source'], ('.fbx',))
            prefab = source_file(source, descriptor['prefab'], ('.prefab',)).read_text(encoding='utf-8')
            if prefab_mesh_guids(prefab) != {metadata_guid(source, descriptor['source'])}:
                raise ValueError('Wardrobe prefab mesh GUID differs from its actual FBX')
            texture = textures['hair']['dark'] if group == 'hair_for_hat' else textures['wardrobe'][f'{style}:nature']
            if 'material' not in texture or prefab_material_guids(prefab) != {metadata_guid(source, texture['material'])}:
                raise ValueError('Wardrobe prefab material GUID differs from its actual palette')
        for descriptor in textures['wardrobe'].values():
            if 'material' not in descriptor:
                raise ValueError('Wardrobe palettes need their actual publisher material')
            material = source_file(source, descriptor['material'], ('.mat',)).read_text(encoding='utf-8')
            match = re.search(r'-(?: _BaseMap| _MainTex):\s*\n\s*m_Texture: \{fileID: \d+, guid: ([a-f0-9]{32})', material)
            if not match or match.group(1) != metadata_guid(source, descriptor['source']):
                raise ValueError('Wardrobe material texture GUID differs from its actual pixels')
        for _, style, module in wardrobe_modules(config):
            if style == 'hair_for_hat':
                continue
            for palette in ('aqua', 'nature', 'fire', 'dark'):
                descriptor = textures['wardrobe'][f'{style}:{palette}']
                prefab = source_file(source, descriptor['prefab'], ('.prefab',)).read_text(encoding='utf-8')
                if prefab_mesh_guids(prefab) != {metadata_guid(source, module['source'])} or prefab_material_guids(prefab) != {metadata_guid(source, descriptor['material'])}:
                    raise ValueError('Wardrobe palette prefab mesh/material GUID differs from its actual sources')
        wardrobe_attachments(source, config)
    return config


def source_map_files(config: dict) -> tuple[str, ...]:
    paths = [*config['bodies'].values(), *config['head'].values(), *config['hair'].values(), config['face'], config['idle']]
    for group in config['textures'].values():
        for descriptor in group.values():
            paths.extend(descriptor.values())
    if config['schema_version'] == 3:
        for _, _, descriptor in wardrobe_modules(config):
            paths.extend((descriptor['source'], descriptor['prefab'], metadata_path(descriptor['source'])))
        for sockets in config['wardrobe']['attachments'].values():
            paths.extend(descriptor['prefab'] for descriptor in sockets.values())
        for path in config['bodies'].values():
            paths.append(metadata_path(path))
        for group in ('wardrobe', 'hair'):
            for descriptor in config['textures'][group].values():
                paths.extend(metadata_path(value) for value in descriptor.values())
    return tuple(sorted(set(paths)))


def wardrobe_modules(config: dict):
    yield 'hair_for_hat', 'hair_for_hat', config['wardrobe']['hair_for_hat']
    for group, styles in WARDROBE_STYLES.items():
        for style in styles:
            yield group, style, config['wardrobe'][group][style]


def metadata_path(path: str) -> str:
    return (path if path.startswith('Unity Metadata/') else 'Unity Metadata/' + path) + '.meta'


def metadata_guid(source: Path, path: str) -> str:
    text = source_file(source, metadata_path(path), ('.meta',)).read_text(encoding='utf-8')
    match = re.search(r'^guid: ([a-f0-9]{32})$', text, re.MULTILINE)
    if not match:
        raise ValueError('Publisher metadata has no bounded GUID')
    return match.group(1)


def prefab_mesh_guids(text: str) -> set[str]:
    return set(re.findall(r'm_Mesh: \{fileID: \d+, guid: ([a-f0-9]{32})', text))


def prefab_material_guids(text: str) -> set[str]:
    matches = re.findall(r'm_Materials:\s*\n((?:\s*-\s*\{[^\n]+\}\s*\n?)+)', text)
    return {guid for block in matches for guid in re.findall(r'guid: ([a-f0-9]{32})', block)}


def prefab_nodes(text: str) -> dict:
    """Read numeric Unity data only; never execute publisher code or scenes."""
    blocks = re.split(r'^--- !u!(\d+) &(-?\d+)(?: stripped)?\s*$', text, flags=re.MULTILINE)
    names, nodes = {}, {}
    for index in range(1, len(blocks), 3):
        kind, identity, block = int(blocks[index]), int(blocks[index + 1]), blocks[index + 2]
        if kind == 1:
            name = re.search(r'^  m_Name: (.+)$', block, re.MULTILINE)
            if name:
                names[identity] = name.group(1).strip()
        if kind != 4 or 'm_LocalPosition:' not in block:
            continue
        references = {}
        for key in ('m_GameObject', 'm_Father'):
            match = re.search(rf'^  {key}: \{{fileID: (-?\d+)\}}$', block, re.MULTILINE)
            if not match:
                raise ValueError('Publisher socket transform reference is invalid')
            references[key] = int(match.group(1))
        node = {'gameobject': references['m_GameObject'], 'parent': references['m_Father']}
        for key, axes in (('position', 'xyz'), ('rotation', 'xyzw'), ('scale', 'xyz')):
            match = re.search(rf'^  m_Local{key.title()}: \{{([^}}]+)\}}$', block, re.MULTILINE)
            if not match:
                raise ValueError('Publisher socket transform is incomplete')
            values = dict(item.strip().split(': ', 1) for item in match.group(1).split(','))
            exact_keys(values, tuple(axes), 'Socket transform components')
            node[key] = [float(values[axis]) for axis in axes]
            if any(not math.isfinite(value) for value in node[key]):
                raise ValueError('Publisher socket transform must be finite')
        if min(node['scale']) <= 0 or abs(math.hypot(*node['rotation']) - 1) > 0.00001:
            raise ValueError('Publisher transform needs positive scale and a unit quaternion')
        nodes[identity] = node
    for node in nodes.values():
        if node['gameobject'] not in names or (node['parent'] and node['parent'] not in nodes):
            raise ValueError('Publisher socket hierarchy is incomplete')
        node['name'] = names[node['gameobject']]
    return nodes


def matrix_product(left: list, right: list) -> list:
    return [[sum(left[row][entry] * right[entry][column] for entry in range(4)) for column in range(4)] for row in range(4)]


def prefab_world(nodes: dict, identity: int, visiting: tuple = ()) -> list:
    if identity in visiting or len(visiting) > 100:
        raise ValueError('Publisher socket hierarchy contains a cycle')
    node = nodes[identity]
    if any(abs(value - 1) > 0.00001 for value in node['scale']):
        raise ValueError('Publisher socket ancestry needs a rigid unit transform')
    x, y, z, w = (value / math.hypot(*node['rotation']) for value in node['rotation'])
    px, py, pz = node['position']
    matrix = [[1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w), px], [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w), py], [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y), pz], [0, 0, 0, 1]]
    # Keep the publisher's tiny serialization scale rounding too.
    for row in range(3):
        for column in range(3):
            matrix[row][column] *= node['scale'][column]
    return matrix_product(prefab_world(nodes, node['parent'], (*visiting, identity)), matrix) if node['parent'] else matrix


def wardrobe_attachments(source: Path, config: dict) -> dict:
    """Derive attachment world transforms from the actual base prefab tree."""
    exact_keys(config['wardrobe']['attachments'], OUTFIT_STYLES, 'Wardrobe costume attachments')
    # Actual FBX imports verify this Unity-left-handed/Y-up to Blender basis.
    basis = [[-1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]]
    inverse = [list(row) for row in zip(*basis)]
    result = {}
    for style, sockets in config['wardrobe']['attachments'].items():
        exact_keys(sockets, tuple(WARDROBE_SOCKETS), 'Wardrobe sockets')
        result[style] = {}
        for socket, descriptor in sockets.items():
            exact_keys(descriptor, ('prefab', 'point', 'bone'), 'Publisher socket source')
            text = source_file(source, descriptor['prefab'], ('.prefab',)).read_text(encoding='utf-8')
            if prefab_mesh_guids(text) != {metadata_guid(source, config['bodies'][style])}:
                raise ValueError('Costume prefab mesh GUID differs from its actual body')
            nodes = prefab_nodes(text)
            points = [key for key, node in nodes.items() if node['name'] == descriptor['point']]
            expected_point, expected_bone = WARDROBE_SOCKETS[socket]
            if descriptor['point'] != expected_point or descriptor['bone'] != expected_bone or len(points) != 1:
                raise ValueError('Publisher socket has the wrong point or parent bone')
            point = points[0]
            parent = nodes[point]['parent']
            if not parent or nodes[parent]['name'] != descriptor['bone']:
                raise ValueError('Publisher socket has the wrong parent bone')
            world = matrix_product(matrix_product(basis, prefab_world(nodes, point)), inverse)
            bone = matrix_product(matrix_product(basis, prefab_world(nodes, parent)), inverse)
            result[style][socket] = {'bone': descriptor['bone'], 'world_matrix': world, 'bone_position': [bone[index][3] for index in range(3)]}
    return result


def publisher_color(path: Path) -> tuple[float, ...]:
    text = path.read_text(encoding='utf-8')
    color_pattern = r': \{r: ([\d.eE+-]+), g: ([\d.eE+-]+), b: ([\d.eE+-]+), a: ([\d.eE+-]+)\}'
    match = re.search(r'- _BaseColor' + color_pattern, text) or re.search(r'- _Color' + color_pattern, text)
    if not match:
        raise ValueError('Supplied material has no Standard Color or URP BaseColor')
    return tuple(float(value) for value in match.groups())


def prepare(source: Path, output: Path, blender: Path) -> dict:
    from PIL import Image

    files = ['FBX/Female Archer 01.FBX', 'Standard Assets Files/FBX/Female Head 02.FBX', 'Standard Assets Files/FBX/Female Face.FBX']
    files.extend(f'Standard Assets Files/FBX/Female Hair {index:02}.FBX' for index in range(1, 5))
    texture_sources = {f'{skin}:{outfit}': f'{skin.title()} {outfit.title()}' for skin, outfit in BODY_PALETTES}
    for name in list(texture_sources.values()) + ['Hair Dark', 'Hair Light', 'Face Female 01 Black', 'Face Female 01 Blonde']:
        files.append(f'Standard Assets Files/Textures/{name}.psd')
    files.extend(f'Standard Assets Files/Materials/{material}.mat' for _, material in HAIR_VARIANTS.values())
    files.append('Standard Assets Files/Animators and Animations/Char@Idle.FBX')
    selected = {relative: source / relative for relative in files}
    if any(not path.is_file() for path in selected.values()):
        raise FileNotFoundError('A recorded Archer source or palette is missing')
    before = {name: sha256(path) for name, path in selected.items()}
    output.mkdir(parents=True, exist_ok=True)
    scratch = ROOT / 'scripts/r3f/private'
    scratch.mkdir(parents=True, exist_ok=True)
    textures = {'outfit': {}, 'hair': {}, 'face': {}}
    texture_metadata = {}

    def convert(name: str, filename: str, tint: tuple[float, ...] = (1, 1, 1, 1)) -> None:
        with Image.open(source / f'Standard Assets Files/Textures/{name}.psd') as original:
            image = original.convert('RGBA')
            image.thumbnail((512, 512), Image.Resampling.LANCZOS)
            channels = image.split()
            image = Image.merge('RGBA', tuple(channel.point(lambda value, factor=factor: round(value * factor)) for channel, factor in zip(channels, tint)))
            image.save(output / filename)
        texture_metadata[filename] = {'sha256': sha256(output / filename), 'bytes': (output / filename).stat().st_size, 'publisher_tint': list(tint)}

    for key, name in texture_sources.items():
        filename = key.replace(':', '-') + '.png'
        convert(name, filename)
        textures['outfit'][key] = filename
    for key, (name, material) in HAIR_VARIANTS.items():
        filename = f'hair-{key}.png'
        convert(name, filename, publisher_color(source / f'Standard Assets Files/Materials/{material}.mat'))
        textures['hair'][key] = filename
        filename = f'face-{key}.png'
        convert('Face Female 01 ' + ('Black' if key == 'dark' else 'Blonde'), filename)
        textures['face'][key] = filename

    config_path = scratch / 'archer-config.json'
    config_path.write_text(json.dumps({'source': str(source), 'output': str(output), 'textures': textures, 'evidence': str(scratch / 'archer-render')}), encoding='utf-8')
    worker = ROOT / 'scripts/r3f/blender_archer.py'
    result = subprocess.run([str(blender), '--background', '--factory-startup', '--python-exit-code', '1', '--python', str(worker), '--', str(config_path)], capture_output=True, text=True, encoding='utf-8', errors='replace')
    (scratch / 'archer-conversion.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Archer conversion failed; inspect private archer-conversion.log')
    if before != {name: sha256(path) for name, path in selected.items()}:
        raise RuntimeError('Original Archer inputs changed')
    model = verify_export(output / 'archer.glb', [])
    if model['skin_count'] != 1:
        raise ValueError('Static Archer lost its supplied body skin')
    manifest = {
        'schema_version': 1, 'delivery_review': 'private_evaluation', 'license_url': LICENSE_URL,
        'models': {'archer': {'file': 'archer.glb', 'idle_clip': None, 'rotation_y': 0, 'scale': 1, **model}},
        'parts': {'body': 'Archer_Body', 'head': 'Archer_Head', 'face': 'Archer_Face', 'hair': {f'hair-{index:02}': f'Archer_Hair_{index:02}' for index in range(1, 5)}},
        'textures': textures, 'texture_metadata': texture_metadata,
        'defaults': {'hair_style': 'hair-01', 'hair_color': 'dark', 'skin_tone': 'fair', 'outfit': 'nature'},
        'capabilities': {'static_pose': True, 'animation': False, 'weapons': False, 'fitted_creature_clothing': False},
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (scratch / 'archer-conversion-report.json').write_text(json.dumps({'input_sha256': before, 'originals_unchanged': True, 'worker_sha256': sha256(worker), 'manifest': manifest, 'validation': json.loads((scratch / 'archer-render/validation.json').read_text(encoding='utf-8'))}, indent=2) + '\n', encoding='utf-8')
    return manifest


def animation_validation(report: object) -> dict:
    """Accept measured conversion evidence, never an owner-review declaration."""
    fields = ('method', 'duration_seconds', 'sampled_frames', 'moving_vertices', 'source_rest_joint_difference', 'target_joint_error', 'rotation_delta_error', 'nonroot_translation_variation', 'source_scale_variation', 'head_attachment_error', 'reimport_max_vertex_error')
    exact_keys(report, fields, 'Animation conversion report')
    if report['method'] != 'supplied-hierarchy-rotation-retarget-v1':
        raise ValueError('Unknown supplied-animation conversion method')
    numeric = fields[1:]
    if any(isinstance(report[key], bool) or not isinstance(report[key], (int, float)) or not math.isfinite(report[key]) for key in numeric):
        raise ValueError('Animation conversion evidence must be finite measurements')
    if any(not isinstance(report[key], int) for key in ('sampled_frames', 'moving_vertices')):
        raise ValueError('Animation sample and vertex counts must be integers')
    if report['duration_seconds'] <= 0 or report['sampled_frames'] < 3 or report['moving_vertices'] <= 0:
        raise ValueError('Supplied Idle needs positive duration and moving reimported skin')
    if report['source_rest_joint_difference'] < 0:
        raise ValueError('Source rest-joint difference must be a nonnegative diagnostic')
    for key, limit in (('target_joint_error', 0.0001), ('rotation_delta_error', 0.0001), ('nonroot_translation_variation', 0.00001), ('source_scale_variation', 0.00001), ('head_attachment_error', 0.0001), ('reimport_max_vertex_error', 0.001)):
        if not 0 <= report[key] <= limit:
            raise ValueError(f'Animation conversion failed {key}')
    return report


def private_staging_parent(output: Path, source: Path) -> Path:
    """Keep even incomplete purchased-art exports outside Git's visible paths."""
    ensure_private_output(output, source)
    parent = ROOT / 'scripts/r3f/private' if output.resolve().is_relative_to(ROOT.resolve()) else output.parent
    ensure_private_output(parent, source)
    return parent


def prepare_modular(source: Path, output: Path, blender: Path, source_map: dict, review_reference: str | None = None, review_colors: tuple[str, ...] = HAIR_COLORS) -> dict:
    """Export actual inventoried palettes and validated supplied Idle privately."""
    config = reviewed_source_map(source, source_map)
    if not review_colors or len(set(review_colors)) != len(review_colors) or any(color not in HAIR_COLORS for color in review_colors):
        raise ValueError('Review colors must be distinct supplied hair colors')
    if review_reference is not None and (not review_reference.strip() or len(review_reference) > 512):
        raise ValueError('Animation review reference must identify an owner review')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Preserve the existing private avatar export; choose an empty output directory')
    stage_parent = private_staging_parent(output, source)
    from PIL import Image

    before = {name: sha256(source / name) for name in source_map_files(config)}
    output.parent.mkdir(parents=True, exist_ok=True)
    scratch = ROOT / 'scripts/r3f/private'
    scratch.mkdir(parents=True, exist_ok=True)
    stage_parent.mkdir(parents=True, exist_ok=True)
    if stage_parent.stat().st_dev != output.parent.stat().st_dev:
        raise ValueError('Private staging and output must share a filesystem for atomic publication')
    textures = {group: {} for group in config['textures']}
    texture_metadata = {}
    deduplicated = {}
    with tempfile.TemporaryDirectory(prefix='.archer-', dir=stage_parent) as staging:
        stage = Path(staging)
        for group, choices in config['textures'].items():
            for key, descriptor in choices.items():
                identity = (descriptor['source'], descriptor.get('material'))
                if identity in deduplicated:
                    textures[group][key] = deduplicated[identity]
                    continue
                filename = f'{group}-{key.replace(":", "-")}.png'
                tint = publisher_color(source / descriptor['material']) if 'material' in descriptor else (1, 1, 1, 1)
                if any(not math.isfinite(value) or not 0 <= value <= 1 for value in tint):
                    raise ValueError('Publisher texture tint must be finite normalized RGBA')
                with Image.open(source / descriptor['source']) as original:
                    image = original.convert('RGBA')
                    image.thumbnail((512, 512), Image.Resampling.LANCZOS)
                    image = Image.merge('RGBA', tuple(channel.point(lambda value, factor=factor: round(value * factor)) for channel, factor in zip(image.split(), tint)))
                    image.save(stage / filename)
                textures[group][key] = filename
                deduplicated[identity] = filename
                texture_metadata[filename] = {'sha256': sha256(stage / filename), 'bytes': (stage / filename).stat().st_size, 'publisher_tint': list(tint)}
        config_path = scratch / 'archer-modular-config.json'
        worker_config = {'schema_version': config['schema_version'], 'source': str(source), 'source_map': config, 'output': str(stage), 'textures': textures, 'evidence': str(scratch / 'archer-modular-render'), 'review_colors': list(review_colors)}
        if config['schema_version'] == 3:
            worker_config['wardrobe_attachments'] = wardrobe_attachments(source, config)
        config_path.write_text(json.dumps(worker_config), encoding='utf-8')
        worker = ROOT / 'scripts/r3f/blender_archer.py'
        worker_sha = sha256(worker)
        result = subprocess.run([str(blender), '--background', '--factory-startup', '--python-exit-code', '1', '--python', str(worker), '--', str(config_path)], capture_output=True, text=True, encoding='utf-8', errors='replace')
        (scratch / 'archer-modular-conversion.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        if result.returncode:
            raise RuntimeError('Modular Archer conversion failed; inspect private archer-modular-conversion.log')
        if sha256(worker) != worker_sha:
            raise RuntimeError('Converter changed during validation; rerun with the unchanged converter')
        if before != {name: sha256(source / name) for name in before}:
            raise RuntimeError('Original Archer inputs changed')
        reports = json.loads((scratch / 'archer-modular-render/validation.json').read_text(encoding='utf-8'))
        exact_keys(reports, OUTFIT_STYLES, 'Costume conversion reports')
        models = {}
        for style in OUTFIT_STYLES:
            model = verify_export(stage / f'{style}.glb', ['Idle'])
            expected_meshes = 18 if config['schema_version'] == 3 else 8
            if model['skin_count'] != 1 or model['mesh_count'] != expected_meshes:
                raise ValueError('Each Archer costume must retain its complete supplied body skin and all reviewed modules')
            models[style] = {
                'file': f'{style}.glb', 'idle_clip': 'Idle', 'rotation_y': 0, 'scale': 1,
                **model, 'animation_source_sha256': before[config['idle']],
                'animation_validation': animation_validation(reports[style]),
            }
            if review_reference is not None:
                models[style]['animation_review_reference'] = review_reference
        manifest = {
            'schema_version': config['schema_version'], 'delivery_review': 'private_evaluation', 'license_url': LICENSE_URL,
            'models': models,
            'parts': {'body': 'Archer_Body', 'head': {key: f'Archer_Head_{index:02}' for index, key in enumerate(HEAD_STYLES, 1)}, 'face': 'Archer_Face', 'hair': {key: f'Archer_Hair_{index:02}' for index, key in enumerate(HAIR_STYLES, 1)}},
            'textures': textures, 'texture_metadata': texture_metadata,
            'defaults': {'outfit_style': 'archer-01', 'face_style': 'face-01', 'head_style': 'head-02', 'hair_style': 'hair-01', 'hair_color': 'dark', 'skin_tone': 'fair', 'outfit': 'nature'},
            'capabilities': {'static_pose': True, 'animation': True, 'weapons': False, 'fitted_creature_clothing': False},
        }
        if config['schema_version'] == 3:
            manifest['parts']['wardrobe'] = wardrobe_parts()
            manifest['defaults'].update({key + '_style': 'none' for key in WARDROBE_STYLES})
            manifest['capabilities']['wardrobe'] = True
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        private_report = {'source_review_reference': config['source_review_reference'], 'input_sha256': before, 'originals_unchanged': True, 'worker_sha256': worker_sha, 'manifest': manifest}
        if config['schema_version'] == 3:
            private_report['wardrobe_attachments'] = worker_config['wardrobe_attachments']
            private_report['wardrobe_validation'] = json.loads((scratch / 'archer-modular-render/wardrobe-validation.json').read_text(encoding='utf-8'))
        (scratch / 'archer-modular-conversion-report.json').write_text(json.dumps(private_report, indent=2) + '\n', encoding='utf-8')
        if output.exists():
            output.rmdir()
        stage.rename(output)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Privately staged Female Archer Pack01 CuteSeries directory')
    parser.add_argument('--output', type=Path, default=ROOT / 'frontend/src/avatar/licensed')
    parser.add_argument('--blender')
    parser.add_argument('--source-map', type=Path, help='Private reviewed v2/v3 source inventory; v3 adds supplied wardrobe with prefab-derived attachments')
    parser.add_argument('--animation-review-reference', help='Existing owner review of the real converted Idle; never grants public delivery')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    ensure_private_output(output, source)
    if args.source_map:
        manifest = prepare_modular(source, output, find_blender(args.blender), json.loads(args.source_map.read_text(encoding='utf-8')), args.animation_review_reference)
        sys.stdout.write('Private three-costume Archer conversion completed; supplied Idle still needs owner acceptance before public delivery.\n')
    else:
        if args.animation_review_reference:
            parser.error('--animation-review-reference requires --source-map')
        manifest = prepare(source, output, find_blender(args.blender))
        sys.stdout.write('Private static Archer exported with four supplied hairstyles and eight outfit/skin palettes; originals unchanged.\n')
    sys.stdout.write(json.dumps({'model_bytes': sum(model['bytes'] for model in manifest['models'].values()), 'texture_bytes': sum(item['bytes'] for item in manifest['texture_metadata'].values()), 'idle_clip': 'Idle' if manifest['schema_version'] >= 2 else None}) + '\n')


if __name__ == '__main__':
    main()
