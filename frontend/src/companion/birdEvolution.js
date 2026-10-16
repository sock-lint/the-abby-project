// These are presentation names for one saved species/potion identity. Growth
// counters and preview controls never grant a stage or a second pet.
export const BIRD_EVOLUTION_STAGES = [
  { id: 'chick', name: 'Chick', growth: '0–49 growth', spriteKey: 'cute-chick' },
  { id: 'fledgling', name: 'Fledgling', growth: 'From 50 growth', spriteKey: 'cute-chick-fledgling' },
  { id: 'bird', name: 'Bird', growth: '100 growth · Confirmed evolution', spriteKey: 'cute-chick-mount' },
];
export const BIRD_STAGES = BIRD_EVOLUTION_STAGES.map(({ id }) => id);

export function isBirdIdentity(species, potion) {
  return species?.slug === 'chick' && species?.sprite_key === 'cute-chick' && potion?.slug === 'base';
}

export function birdStage(creature, kind = 'pet') {
  if (!creature?.id || !isBirdIdentity(creature.species, creature.potion)) return null;
  if (kind === 'mount' || creature.evolved_to_mount === true) return 'bird';
  // A confirmed evolution flag/mount is required for Bird, even if a stale
  // payload says 100 growth. The intermediate stage comes from Django too.
  if (creature.evolution_stage !== undefined && creature.evolution_stage !== null) {
    return ['chick', 'fledgling'].includes(creature.evolution_stage) ? creature.evolution_stage : null;
  }
  return 'chick';
}

export function birdFormName(species, potion, stage) {
  return isBirdIdentity(species, potion)
    ? BIRD_EVOLUTION_STAGES.find(({ id }) => id === stage)?.name || species?.name
    : species?.name;
}
