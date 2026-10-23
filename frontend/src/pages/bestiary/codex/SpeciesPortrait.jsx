import RpgSprite from '../../../components/rpg/RpgSprite';
import { petSpriteKeys } from '../../../components/rpg/petSpriteKeys';
import { ownedSpeciesCreature } from '../../../companion/previewAccess';

/**
 * Discovered-species portrait. ``ownership`` is undefined for parents and
 * staff, who keep the species portrait. For a child it is the stable
 * response (or null while unknown): only an exact appearance they own is
 * drawn, never Base as a stand-in, and unknown ownership shows the icon.
 */
export default function SpeciesPortrait({ species, ownership, size }) {
  if (ownership === undefined) {
    return <RpgSprite spriteKey={species.sprite_key} icon={species.icon} size={size} alt={species.name} />;
  }
  const owned = ownedSpeciesCreature(ownership, species);
  if (!owned) return <RpgSprite icon={species.icon} size={size} alt={species.name} />;
  return <RpgSprite {...petSpriteKeys(owned.creature, owned.kind)} icon={species.icon} size={size}
    alt={species.name} potionSlug={owned.creature.potion?.slug} />;
}
