import { BIRD_EVOLUTION_STAGES, birdStage, isBirdIdentity } from '../../companion/birdEvolution';

export default function PetEvolutionGuide({ species, potion, creature, kind = 'pet' }) {
  if (!isBirdIdentity(species || creature?.species, potion || creature?.potion)) return null;
  const current = birdStage(creature, kind);
  return (
    <ol aria-label="Pet growth stages" className="grid grid-cols-1 sm:grid-cols-3 gap-2">
      {BIRD_EVOLUTION_STAGES.map(({ id, name, growth }) => (
        <li key={id} aria-current={id === current ? 'step' : undefined}
          className={`rounded-xl border p-3 ${id === current ? 'border-sheikah-teal-deep bg-sheikah-teal/10' : 'border-ink-page-shadow bg-ink-page-aged'}`}>
          <div className="text-body font-semibold text-ink-primary">{name}</div>
          <p className="text-caption text-ink-secondary">{growth}</p>
        </li>
      ))}
    </ol>
  );
}
