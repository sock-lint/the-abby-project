const record = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const text = (value) => typeof value === 'string' && value.trim().length > 0 && value.length <= 120;
const key = (value) => typeof value === 'string' && /^[a-z][a-z0-9_-]{0,63}$/.test(value);
const exactKeys = (value, keys) => record(value) && Object.keys(value).length === keys.length && keys.every((field) => Object.hasOwn(value, field));

export function resolveAvatarCatalog(catalog) {
  if (catalog?.schema_version !== 1 || !Array.isArray(catalog.avatars) || !catalog.avatars.length
    || !Array.isArray(catalog.accessory_slots) || !catalog.accessory_slots.length || !record(catalog.accessories)) return null;
  const slots = catalog.accessory_slots.map((slot) => slot?.id);
  if (new Set(slots).size !== slots.length || catalog.accessory_slots.some((slot) => !key(slot?.id) || !text(slot?.label))
    || Object.entries(catalog.accessories).some(([id, item]) => !key(id) || !text(item?.label))) return null;
  const avatars = [];
  const ids = new Set();
  for (const avatar of catalog.avatars) {
    if (!key(avatar?.id) || ids.has(avatar.id) || !text(avatar.label) || !key(avatar.renderer_adapter)
      || !record(avatar.defaults?.appearance) || !exactKeys(avatar.defaults?.accessories, slots)
      || !exactKeys(avatar.accessory_bindings, slots) || !Array.isArray(avatar.groups) || !avatar.groups.length
      || !Array.isArray(avatar.presets)) return null;
    ids.add(avatar.id);
    const appearance = new Set();
    const accessories = new Set();
    const groupIds = new Set();
    const groups = [];
    for (const group of avatar.groups) {
      if (!key(group?.id) || groupIds.has(group.id) || !text(group.label) || !Array.isArray(group.fields) || !group.fields.length) return null;
      groupIds.add(group.id);
      const fields = [];
      for (const field of group.fields) {
        if (!key(field?.key) || !text(field.label) || !Array.isArray(field.choices) || !field.choices.length) return null;
        const slot = field.accessory_slot;
        const values = field.choices.map((choice) => choice?.value);
        if (new Set(values).size !== values.length || values.some((value) => typeof value !== 'string')) return null;
        let choices;
        if (slot !== undefined) {
          const binding = avatar.accessory_bindings[slot];
          if (slot !== field.key || !slots.includes(slot) || accessories.has(slot) || !record(binding)
            || !Array.isArray(binding.item_ids) || new Set(binding.item_ids).size !== binding.item_ids.length
            || binding.item_ids.some((id) => !Object.hasOwn(catalog.accessories, id))
            || values.length !== binding.item_ids.length + 1 || !values.includes('none')
            || binding.item_ids.some((id) => !values.includes(id)) || avatar.defaults.accessories[slot] !== 'none') return null;
          accessories.add(slot);
          choices = [];
          for (const choice of field.choices) {
            if (choice.value === 'none') choices.push({ value: 'none', label: 'None' });
            else {
              if (choice.accessory_id !== choice.value || !binding.item_ids.includes(choice.value)) return null;
              choices.push({ value: choice.value, label: catalog.accessories[choice.value].label });
            }
          }
        } else {
          if (appearance.has(field.key) || !values.includes(avatar.defaults.appearance[field.key])
            || field.choices.some((choice) => !text(choice.label))) return null;
          appearance.add(field.key); choices = field.choices;
        }
        fields.push({ ...field, choices });
      }
      groups.push({ ...group, fields });
    }
    if (!exactKeys(avatar.defaults.appearance, [...appearance]) || accessories.size !== slots.length) return null;
    const resolved = { ...avatar, groups };
    const presetIds = new Set();
    for (const preset of avatar.presets) {
      if (!key(preset?.id) || presetIds.has(preset.id) || !text(preset.label)
        || !record(preset.appearance) || !record(preset.accessories)
        || [...Object.keys(preset.appearance), ...Object.keys(preset.accessories)].length === 0
        || !validPatch(resolved, preset)) return null;
      presetIds.add(preset.id);
    }
    avatars.push(resolved);
  }
  return ids.has(catalog.default_avatar_id) ? { ...catalog, avatars } : null;
}

export function defaultAvatarDefinition(catalog) {
  return resolveAvatarCatalog(catalog)?.avatars.find((avatar) => avatar.id === catalog.default_avatar_id) || null;
}
export function avatarDefinition(catalog, id) { return catalog.avatars.find((avatar) => avatar.id === id) || null; }
export function defaultConfiguration(avatar) {
  return { avatar_id: avatar.id, appearance: { ...avatar.defaults.appearance }, accessories: { ...avatar.defaults.accessories } };
}
function validPatch(avatar, patch) {
  return avatar.groups.every((group) => group.fields.every((field) => {
    const values = field.accessory_slot ? patch.accessories : patch.appearance;
    return !Object.hasOwn(values, field.key) || field.choices.some((choice) => choice.value === values[field.key]);
  })) && Object.keys(patch.appearance).every((key) => Object.hasOwn(avatar.defaults.appearance, key))
    && Object.keys(patch.accessories).every((key) => Object.hasOwn(avatar.defaults.accessories, key));
}
export function validConfiguration(catalog, configuration, expectedAvatarId = configuration?.avatar_id) {
  const avatar = avatarDefinition(catalog, expectedAvatarId);
  return !!avatar && configuration?.avatar_id === expectedAvatarId
    && exactKeys(configuration.appearance, Object.keys(avatar.defaults.appearance))
    && exactKeys(configuration.accessories, Object.keys(avatar.defaults.accessories))
    && validPatch(avatar, configuration);
}
export function editableConfiguration(catalog, configuration) {
  const avatar = avatarDefinition(catalog, configuration?.avatar_id);
  // Unknown saved values stay visible as unavailable choices; editing must
  // never silently exchange an older item for None or another base avatar.
  return !!avatar && exactKeys(configuration.appearance, Object.keys(avatar.defaults.appearance))
    && exactKeys(configuration.accessories, Object.keys(avatar.defaults.accessories))
    && [...Object.values(configuration.appearance), ...Object.values(configuration.accessories)].every((value) => typeof value === 'string');
}
export function patchConfiguration(catalog, configuration, patch) {
  const avatar = avatarDefinition(catalog, configuration.avatar_id);
  const next = { avatar_id: configuration.avatar_id, appearance: { ...configuration.appearance, ...patch.appearance }, accessories: { ...configuration.accessories, ...patch.accessories } };
  return validPatch(avatar, { appearance: patch.appearance || {}, accessories: patch.accessories || {} }) ? next : configuration;
}
export function sameConfiguration(left, right) {
  if (!record(left) || !record(right) || !record(left.appearance) || !record(left.accessories)
    || !record(right.appearance) || !record(right.accessories)) return JSON.stringify(left) === JSON.stringify(right);
  return left.avatar_id === right.avatar_id && ['appearance', 'accessories'].every((scope) =>
    Object.keys(left[scope]).length === Object.keys(right[scope]).length && Object.entries(left[scope]).every(([key, value]) => right[scope][key] === value));
}
export function switchAvatarConfiguration(catalog, configuration, id) {
  const avatar = avatarDefinition(catalog, id);
  const next = defaultConfiguration(avatar);
  const removed = [];
  for (const [slot, item] of Object.entries(record(configuration?.accessories) ? configuration.accessories : {})) {
    if (item === 'none') continue;
    if (avatar.accessory_bindings[slot]?.item_ids.includes(item)) next.accessories[slot] = item;
    else removed.push(catalog.accessories[item]?.label || 'Unavailable saved item');
  }
  return { configuration: next, removed };
}
