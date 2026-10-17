import { birdStage } from '../../companion/birdEvolution';
import { rosterFamily } from '../../companion/sharedRosterRelease';

// Growth alone never unlocks an evolved portrait. The server keeps the pet
// row after evolution, so those rows use the confirmed mount form too.
export function petSpriteKeys(pet, kind = 'pet') {
  const base = pet?.species?.sprite_key || null;
  if (rosterFamily(pet?.species, pet?.potion)) {
    const stage = kind === 'mount' || pet?.evolved_to_mount === true ? 'grown' : ['baby', 'middle'].includes(pet.lifecycle_stage) ? pet.lifecycle_stage : null;
    return { spriteKey: stage === 'grown' ? `${base}-mount` : stage === 'middle' ? `${base}-middle` : stage === 'baby' ? base : null, fallbackSpriteKey: null };
  }
  if (base?.startsWith('meshtint-')) return { spriteKey: null, fallbackSpriteKey: null };
  if (birdStage(pet) === 'fledgling') return { spriteKey: 'cute-chick-fledgling', fallbackSpriteKey: base };
  const evolved = (kind === 'mount' || pet?.evolved_to_mount === true) && Boolean(base);
  return {
    spriteKey: evolved ? `${base}-mount` : base,
    fallbackSpriteKey: evolved ? base : null,
  };
}
