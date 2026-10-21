export const isTaxonomyAvailable = (entry) => !entry.is_retired && entry.available_for_new_choices !== false;

export function taxonomyStatus(entry, kind = 'skill') {
  if (entry.is_retired) return 'Retired';
  if (isTaxonomyAvailable(entry)) return '';
  return kind === 'skill' ? 'Unavailable for new choices (category or subject retired)'
    : kind === 'subject' ? 'Unavailable for new choices (category retired)' : 'Unavailable for new choices';
}

export function taxonomyOptionLabel(entry, label = entry.name, kind = 'skill') {
  const status = taxonomyStatus(entry, kind);
  // Quote authored text containing the separator so it cannot impersonate a
  // lifecycle suffix or a retained-ID placeholder. JSON escaping also keeps
  // literal quotation marks distinct without changing numeric option values.
  const authored = [entry.icon, label].filter(Boolean).join(' ');
  const name = authored.includes(' · ') ? JSON.stringify(String(label)) : label;
  return status ? `${name} · ${status}` : name;
}

export function taxonomyChoices(entries, selected = []) {
  const ids = new Set((Array.isArray(selected) ? selected : [selected]).map(String));
  return entries.filter((entry) => isTaxonomyAvailable(entry) || ids.has(String(entry.id)));
}
