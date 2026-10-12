// Availability controls new catalog actions. Existing ownership remains usable
// in a separate collection. Missing flags preserve older response compatibility.
export function isCatalogAvailable(entity) {
  return entity?.catalog_available !== false
    && entity?.species?.catalog_available !== false
    && entity?.potion?.catalog_available !== false;
}

export function availableInventoryActions(entry) {
  if (isCatalogAvailable(entry.item)) return entry.available_actions || [];
  // Stored items cannot start another acquisition or equip unsupported art.
  return (entry.available_actions || []).filter((action) => !['equip', 'hatch', 'breed'].includes(action.id)
    && !['/sigil', '/profile', '/bestiary?tab=hatchery'].includes(action.to));
}
