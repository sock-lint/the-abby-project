import lifecycle from '../../../shared/catalog/companion-lifecycle.json';
import { birdStage } from './birdEvolution';
import { rosterEggFamily } from './sharedRosterRelease';

export const COMPANION_STAGES = lifecycle.stages;

// Django owns stage changes. Growth counters alone must never select a new
// form, and egg items stay in inventory until the existing hatch succeeds.
export function companionStage(creature, kind = 'pet') {
  if (!creature) return null;
  if (creature.item_type === 'egg') return 'egg';
  if (kind === 'mount' || creature.evolved_to_mount === true) return 'grown';
  if (!creature.id || !creature.species) return null;
  if (creature.lifecycle_stage != null) {
    return ['baby', 'middle'].includes(creature.lifecycle_stage) ? creature.lifecycle_stage : null;
  }
  return birdStage(creature, kind) === 'fledgling' ? 'middle' : 'baby';
}

export function companionStageLabel(creature, kind = 'pet') {
  return lifecycleStageLabel(companionStage(creature, kind));
}

export function lifecycleStageLabel(stage) {
  return COMPANION_STAGES.find(({ id }) => id === stage)?.label || '';
}

export function companionFormName(species, potion, stage) {
  return companionLifecycle(species, potion).find(({ id }) => id === stage)?.form || species?.name;
}

export function companionLifecycle(species, potion) {
  const forms = lifecycle.family_forms.find((family) => family.species_slug === species?.slug
    && family.sprite_key === species?.sprite_key && family.potion_slugs.includes(potion?.slug))?.names;
  const descriptions = {
    egg: 'Hatch with a compatible potion',
    baby: `After hatching · 0–${lifecycle.middle_growth - 1} growth`,
    middle: `From ${lifecycle.middle_growth} growth`,
    grown: `${lifecycle.grown_growth} growth · Confirmed evolution`,
  };
  return COMPANION_STAGES.map((stage) => ({
    ...stage,
    form: forms?.[stage.id] && forms[stage.id] !== stage.label ? forms[stage.id] : null,
    description: descriptions[stage.id],
  }));
}

// An egg's declared family is metadata, never a model or acquisition grant.
export function eggSpecies(item) {
  if (item?.item_type !== 'egg' || !item.pet_species_slug) return null;
  const family = rosterEggFamily(item);
  const chick = item.slug === 'chick-egg' && item.pet_species_slug === 'chick' && item.metadata?.species === 'chick';
  const spriteKey = family?.sprite_key || (chick ? 'cute-chick' : null);
  return { slug: item.pet_species_slug, name: item.pet_species_name || item.pet_species_slug,
    ...(spriteKey ? { sprite_key: spriteKey } : {}) };
}
