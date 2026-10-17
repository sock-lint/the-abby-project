import { companionLifecycle, companionStage } from '../../companion/lifecycle';

export default function PetEvolutionGuide({ species, potion, creature, kind = 'pet', currentStage }) {
  const family = species || creature?.species;
  if (!family) return null;
  const current = currentStage === 'egg' ? 'egg' : companionStage(creature, kind);
  return (
    <ol aria-label="Pet growth stages" className="grid grid-cols-2 lg:grid-cols-4 gap-2">
      {companionLifecycle(family, potion || creature?.potion).map(({ id, label, form, description }) => (
        <li key={id} aria-current={id === current ? 'step' : undefined}
          className={`rounded-xl border p-3 ${id === current ? 'border-sheikah-teal-deep bg-sheikah-teal/10' : 'border-ink-page-shadow bg-ink-page-aged'}`}>
          <div className="text-body font-semibold text-ink-primary">{label}{form ? ` · ${form}` : ''}</div>
          <p className="text-caption text-ink-secondary">{description}</p>
        </li>
      ))}
    </ol>
  );
}
