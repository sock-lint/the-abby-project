import CatalogCard from './CatalogCard';
import EmptyState from '../../components/EmptyState';

/**
 * MountsBlock — parent-only browse of every pet species' evolved mount sprite.
 *
 * Mounts aren't a separate catalog table — they're a species × potion derivation.
 * We render one tile per PetSpecies using the `{sprite_key}-mount` convention
 * (same one Stable.jsx uses) with `fallbackSpriteKey={sprite_key}` so species
 * without a drawn mount sprite still render something recognizable.
 */
export default function MountsBlock({ species, onSelect }) {
  if (!species.length) {
    return (
      <EmptyState>
        No pet species authored yet. Add entries to content/rpg/initial/pet_species.yaml.
      </EmptyState>
    );
  }
  return (
    <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
      {species.map((s) => (
        <CatalogCard
          key={s.id}
          rarity="rare"
          icon={s.icon}
          spriteKey={`${s.sprite_key}-mount`}
          fallbackSpriteKey={s.sprite_key}
          name={s.name}
          subtitle="mount"
          onClick={() => onSelect(s)}
        />
      ))}
    </div>
  );
}
