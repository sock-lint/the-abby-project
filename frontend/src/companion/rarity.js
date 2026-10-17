import { RARITY_KEYS } from '../components/atlas/mastery.constants';

// Potion color and growth do not define a family's acquisition tier. Higher
// rarity saved potion variants keep their original rarity in Saved collection.
export function acquisitionRarity(species, potion) {
  return [species?.rarity, potion?.rarity].reduce((highest, rarity) => (
    RARITY_KEYS.indexOf(rarity) > RARITY_KEYS.indexOf(highest) ? rarity : highest
  ), 'common');
}

export function companionRarity(companion) {
  return RARITY_KEYS.includes(companion?.rarity)
    ? companion.rarity
    : acquisitionRarity(companion?.species, companion?.potion);
}
