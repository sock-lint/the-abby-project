export function initialEditor(section, row, key) {
  let values = row?.values ?? (section === 'items'
    ? { slug: '', name: '', description: '', icon: '✨', sprite_key: '', item_type: 'food', rarity: 'common', coin_value: 0, metadata: {} }
    : { name: '', description: '', icon: '⭐', sprite_key: '', quest_type: 'collection', target_value: 5, duration_days: 7, coin_reward: 0, xp_reward: 0, is_repeatable: false, is_cooperative: false, trigger_filter: {}, required_badge: null, reward_items: [], skill_tags: [] });
  if (section === 'items' && row?.id) {
    values = Object.fromEntries(Object.entries(values).filter(([field]) => !['rarity', 'coin_value', 'metadata'].includes(field)));
  }
  const filters = { ...(values.trigger_filter ?? {}) };
  delete filters.allowed_triggers;
  return {
    section, object_id: row?.id ?? null, key: key ?? `${section}-${row.id}`, values: structuredClone(values),
    metadataText: JSON.stringify(values.metadata ?? row?.metadata ?? {}, null, 2), filterText: JSON.stringify(filters, null, 2),
  };
}

export function editorChange(editor) {
  const values = { ...editor.values };
  const parseObject = (text, label) => {
    let parsed;
    try { parsed = JSON.parse(text); } catch { throw new Error(`${label} must be a valid JSON object.`); }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error(`${label} must be a JSON object.`);
    return parsed;
  };
  if (editor.section === 'items') {
    if (!editor.object_id) values.metadata = parseObject(editor.metadataText, 'Item properties');
    else for (const field of ['rarity', 'coin_value', 'metadata']) delete values[field];
  }
  else {
    const filters = parseObject(editor.filterText, 'Additional activity filters');
    if ('allowed_triggers' in filters) throw new Error('Choose qualifying activities using the activity controls.');
    values.trigger_filter = { ...filters, ...(values.trigger_filter.allowed_triggers?.length ? { allowed_triggers: values.trigger_filter.allowed_triggers } : {}) };
  }
  return { section: editor.section, object_id: editor.object_id, key: editor.key, values };
}

export function itemVersion(row, items) {
  const base = (row.slug || `item-${row.id}`).slice(0, 92);
  let version = 2;
  while (items.some((item) => item.slug === `${base}-v${version}`)) version += 1;
  const source = { ...row, ...row.values };
  const fields = ['name', 'description', 'icon', 'sprite_key', 'item_type', 'rarity', 'coin_value', 'metadata'];
  const values = Object.fromEntries(fields.map((field) => [field, structuredClone(source[field])]).filter(([, value]) => value !== undefined));
  values.slug = `${base}-v${version}`;
  values.name = `${row.name.slice(0, 90)} v${version}`;
  if (row.food_species_id) values.food_species_id = row.food_species_id;
  return { ...row, ...values, id: null, key: crypto.randomUUID(), _changeKey: null, values, editable: true, used_by: {}, runtime_available: undefined };
}
