import { describe, expect, it } from 'vitest';
import { availableInventoryActions, isCatalogAvailable } from './catalogAvailability';

describe('catalog availability', () => {
  it('respects explicit item and owned species/potion restrictions while accepting old response shapes', () => {
    expect(isCatalogAvailable({})).toBe(true);
    expect(isCatalogAvailable({ catalog_available: false })).toBe(false);
    expect(isCatalogAvailable({ species: { catalog_available: false }, potion: {} })).toBe(false);
    expect(isCatalogAvailable({ species: {}, potion: { catalog_available: false } })).toBe(false);
  });
  it('keeps safe stored-item actions but prevents another unavailable hatch or equip', () => {
    const actions = [{ id: 'hatch', to: '/bestiary?tab=hatchery' }, { id: 'equip', to: '/sigil' }, { id: 'open' }];
    expect(availableInventoryActions({ item: { catalog_available: false }, available_actions: actions })).toEqual([{ id: 'open' }]);
  });
});
