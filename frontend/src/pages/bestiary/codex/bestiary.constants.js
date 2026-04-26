// Pure-data exports for the Bestiary Codex. Lives in a `.js` file (not
// `.jsx`) so the `react-refresh/only-export-components` lint rule stays
// satisfied — the tile + detail components share these helpers.

// Truncate description to one short sentence for the tile preview. We
// fall back to the description itself when there's no terminator.
export function loreOneLiner(description, max = 90) {
  if (!description) return '';
  const trimmed = description.trim();
  const dot = trimmed.indexOf('.');
  const candidate = dot > 0 ? trimmed.slice(0, dot + 1) : trimmed;
  if (candidate.length <= max) return candidate;
  return candidate.slice(0, max - 1).trimEnd() + '…';
}

// Mount sprite key convention — see CLAUDE.md "Mount sprite convention".
export function mountSpriteKey(speciesSpriteKey) {
  if (!speciesSpriteKey) return '';
  return `${speciesSpriteKey}-mount`;
}

// Compose the human-readable mount label from species + potion (mirrors
// the "Fire Dragon" composition used by Companions.jsx + Mounts.jsx).
export function mountLabel(speciesName, potionName) {
  return `${potionName} ${speciesName}`;
}
