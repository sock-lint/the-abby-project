export const ordinaryRequirements = {
  total_minutes: 240, min_minutes_per_type: 90, activity_types_required: 2,
  minutes_per_search_type: null, chance_percent: null, guaranteed_search: null, required_hatched_species: 0,
  minutes_per_search: null, max_minutes_per_type_per_search: null,
};
export const rareRequirements = {
  total_minutes: null, min_minutes_per_type: null, activity_types_required: 2,
  minutes_per_search_type: 30, chance_percent: 20, guaranteed_search: 5, required_hatched_species: 2,
  minutes_per_search: 60, max_minutes_per_type_per_search: 30,
};

export const buildEggOffer = (over = {}) => ({
  key: 'wolf-base', name: 'Wolf Egg', tier: 'ordinary',
  egg_item: { id: 71, name: 'Wolf Egg', icon: '🥚', sprite_key: 'big-egg' },
  potion_name: 'Base', eligible: true, unavailable_reason: null, season: null,
  requirements: ordinaryRequirements, ...over,
});
export const buildEggDiscovery = (over = {}) => ({
  ...buildEggOffer(), id: 1, offer_key: 'wolf-base', status: 'active', can_resume: false,
  minutes: { reading: 45, movement: 15, practice: 0 }, searches: [], receipt: null,
  remaining_searches: null, ...over,
});
export const buildEggEnvelope = (over = {}) => ({ enabled: true, offers: [buildEggOffer()], discoveries: [], active_id: null, ...over });
