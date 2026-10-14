import { describe, expect, it } from 'vitest';
import { avatarDefinition, defaultAvatarDefinition, defaultConfiguration, editableConfiguration, patchConfiguration, resolveAvatarCatalog, sameConfiguration, switchAvatarConfiguration, validConfiguration } from './catalog';
import { archerConfiguration, syntheticCatalog } from './catalog.fixtures';

describe('shared compatible avatar catalog', () => {
  it('resolves global labels without filtering by source pack and retains shared bows and quivers across bases', () => {
    const catalog = resolveAvatarCatalog(syntheticCatalog);
    expect(defaultAvatarDefinition(syntheticCatalog).id).toBe('female-archer');
    const knight = avatarDefinition(catalog, 'synthetic-knight');
    expect(knight.groups[1].fields.find((field) => field.key === 'left_hand').choices).toContainEqual({ value: 'bow-greenhorn', label: 'Greenhorn bow' });
    const original = { ...archerConfiguration, accessories: { ...archerConfiguration.accessories, headwear: 'hood-mystical', left_hand: 'bow-greenhorn', back: 'quiver-rook' } };
    const next = switchAvatarConfiguration(catalog, original, knight.id);
    expect(next.configuration).toEqual({ avatar_id: knight.id, appearance: { armor_style: 'steel', crest_style: 'none' }, accessories: { headwear: 'none', face_accessory: 'none', left_hand: 'bow-greenhorn', right_hand: 'none', back: 'quiver-rook' } });
    expect(next.removed).toEqual(['Mystical hood']);
    expect(original.accessories.headwear).toBe('hood-mystical');
    expect(validConfiguration(catalog, next.configuration)).toBe(true);
  });

  it('keeps unknown saved values visible but rejects invalid or incomplete save receipts', () => {
    const catalog = resolveAvatarCatalog(syntheticCatalog);
    const unknown = { ...archerConfiguration, accessories: { ...archerConfiguration.accessories, back: 'retired-item' } };
    expect(editableConfiguration(catalog, unknown)).toBe(true);
    expect(validConfiguration(catalog, unknown)).toBe(false);
    for (const invalid of [null, {}, { ...archerConfiguration, avatar_id: 'unknown' }, { ...archerConfiguration, appearance: {} }, { ...archerConfiguration, accessories: {} }, { ...archerConfiguration, accessories: { ...archerConfiguration.accessories, unknown: 'none' } }]) expect(validConfiguration(catalog, invalid, 'female-archer')).toBe(false);
    expect(editableConfiguration(catalog, { ...unknown, avatar_id: 'unavailable' })).toBe(false);
  });

  it('uses only declared patch fields and detects structured unsaved edits', () => {
    const catalog = resolveAvatarCatalog(syntheticCatalog);
    const current = defaultConfiguration(defaultAvatarDefinition(syntheticCatalog));
    const patched = patchConfiguration(catalog, current, { accessories: { left_hand: 'bow-greenhorn' } });
    expect(sameConfiguration(current, patched)).toBe(false);
    expect(patchConfiguration(catalog, current, { accessories: { user_id: 'other-family' } })).toBe(current);
    expect(patchConfiguration(catalog, current, { appearance: { outfit: 'missing' } })).toBe(current);
    expect(sameConfiguration(null, null)).toBe(true);
  });

  it.each([
    (catalog) => { catalog.schema_version = 9; },
    (catalog) => { catalog.default_avatar_id = 'unknown'; },
    (catalog) => { catalog.accessory_slots[0] = null; },
    (catalog) => { catalog.accessory_slots.push(catalog.accessory_slots[0]); },
    (catalog) => { catalog.accessories['bow-greenhorn'].label = ''; },
    (catalog) => { catalog.avatars[0].defaults.accessories = {}; },
    (catalog) => { catalog.avatars[0].groups[0].fields.push(catalog.avatars[0].groups[0].fields[0]); },
    (catalog) => { catalog.avatars[0].groups[1].fields[0].choices[1].accessory_id = 'wrong'; },
    (catalog) => { catalog.avatars[0].accessory_bindings.headwear.item_ids.push('unknown'); },
    (catalog) => { catalog.avatars[0].presets[0].accessories.left_hand = 'shield-round'; },
  ])('rejects a partial or contradictory catalog before presenting controls', (breakCatalog) => {
    const catalog = structuredClone(syntheticCatalog);
    breakCatalog(catalog);
    expect(resolveAvatarCatalog(catalog)).toBeNull();
  });
});
