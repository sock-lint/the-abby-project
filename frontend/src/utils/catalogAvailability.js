// Availability controls new catalog actions. Existing ownership remains usable
// in a separate collection. Missing flags preserve older response compatibility.
export function isCatalogAvailable(entity) {
  return entity?.catalog_available !== false
    && entity?.species?.catalog_available !== false
    && entity?.potion?.catalog_available !== false;
}

export function availableInventoryActions(entry) {
  const actions = (entry.available_actions || []).filter((action) => action.id !== 'breed');
  if (isCatalogAvailable(entry.item)) return actions;
  // Stored items cannot start another acquisition or equip unsupported art.
  return actions.filter((action) => !['equip', 'hatch'].includes(action.id)
    && !['/sigil', '/profile', '/bestiary?tab=hatchery'].includes(action.to));
}
