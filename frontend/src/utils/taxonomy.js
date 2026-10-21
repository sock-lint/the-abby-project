export const isTaxonomyAvailable = (entry) => !entry.is_retired && entry.available_for_new_choices !== false;

export function taxonomyStatus(entry, kind = 'skill') {
  if (entry.is_retired) return 'Retired';
  if (isTaxonomyAvailable(entry)) return '';
  return kind === 'skill' ? 'Unavailable for new choices (category or subject retired)'
    : kind === 'subject' ? 'Unavailable for new choices (category retired)' : 'Unavailable for new choices';
}

export function taxonomyOptionLabel(entry, label = entry.name, kind = 'skill') {
  const status = taxonomyStatus(entry, kind);
  return status ? `${label} · ${status}` : label;
}

export function taxonomyChoices(entries, selected = []) {
  const ids = new Set((Array.isArray(selected) ? selected : [selected]).map(String));
  return entries.filter((entry) => isTaxonomyAvailable(entry) || ids.has(String(entry.id)));
}
