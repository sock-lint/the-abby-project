#!/usr/bin/env python
"""Convert recorded owned modular Archer sources for private avatar review.

No original inputs are modified, no new clothing is fitted and no skeletal
animation is authored. The selected publisher body/head/face/hair geometry and
palette textures form a static avatar. Original Idle remains unaccepted because
its bind matrices differ from the body rig; it is never silently retargeted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from prepare_meshtint import ROOT, LICENSE_URL, ensure_private_output, find_blender, sha256, verify_export

BODY_PALETTES = [(skin, outfit) for skin in ('fair', 'tan') for outfit in ('aqua', 'nature', 'fire', 'dark')]
HAIR_VARIANTS = {'dark': ('Hair Dark', 'Hair Black'), 'light': ('Hair Light', 'Hair Blonde')}


def publisher_color(path: Path) -> tuple[float, ...]:
    match = re.search(r'- _BaseColor: \{r: ([\d.eE+-]+), g: ([\d.eE+-]+), b: ([\d.eE+-]+), a: ([\d.eE+-]+)\}', path.read_text(encoding='utf-8'))
    if not match:
        raise ValueError('Supplied material has no BaseColor')
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Privately staged Female Archer Pack01 CuteSeries directory')
    parser.add_argument('--output', type=Path, default=ROOT / 'frontend/src/avatar/licensed')
    parser.add_argument('--blender')
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    ensure_private_output(output, source)
    manifest = prepare(source, output, find_blender(args.blender))
    print('Private static Archer exported with four supplied hairstyles and eight outfit/skin palettes; originals unchanged.')
    print(json.dumps({'model_bytes': manifest['models']['archer']['bytes'], 'texture_bytes': sum(item['bytes'] for item in manifest['texture_metadata'].values()), 'idle_clip': None}))


if __name__ == '__main__':
    main()
