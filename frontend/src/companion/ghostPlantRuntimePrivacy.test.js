import { readFileSync, readdirSync } from 'node:fs';
import { basename, join, relative, resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import runtime from '../../../shared/catalog/elemental-ghost-potted-plant.runtime.json';

const sourceRoot = resolve(process.cwd(), 'src');
const auditDescriptor = 'elemental-ghost-potted-plant.json';

function productionSources(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return entry.name === 'test' ? [] : productionSources(path);
    return /\.[jt]sx?$/.test(entry.name) && !/\.test\.[jt]sx?$/.test(entry.name) ? [path] : [];
  });
}

describe('Ghost and Potted Plant runtime privacy', () => {
  it('preserves every release and family value from the audit descriptor', () => {
    const audit = JSON.parse(readFileSync(resolve(sourceRoot, '../../shared/catalog', auditDescriptor), 'utf8'));
    expect(runtime).toEqual({ release: audit.release, families: audit.families });
  });

  it('allows only public runtime fields at every descriptor level', () => {
    const keys = (value) => Object.keys(value).sort();
    expect(keys(runtime)).toEqual(['families', 'release']);
    expect(keys(runtime.release)).toEqual(['family_id', 'manifest_sha256', 'release_version']);
    for (const family of runtime.families) {
      expect(keys(family)).toEqual(['challenges', 'egg_item_slug', 'review_icons', 'species_slug', 'sprite_key']);
      for (const challenge of family.challenges) {
        expect(keys(challenge)).toEqual(['catalog_icon', 'name', 'potion_slug', 'target_count', 'window_days']);
      }
      for (const icon of family.review_icons) expect(keys(icon)).toEqual(['asset_id', 'potion_slug']);
    }
  });

  it('keeps the private audit descriptor out of production imports', () => {
    const references = productionSources(sourceRoot).flatMap((path) => {
      const imports = readFileSync(path, 'utf8').matchAll(/(?:\bfrom\s*|\bimport\s*\(\s*)['"]([^'"]+)['"]/g);
      return [...imports].filter(([, specifier]) => basename(specifier.split('?')[0]) === auditDescriptor)
        .map(() => relative(sourceRoot, path));
    });
    expect(references).toEqual([]);
  });
});
