import { companionLifecycle, companionStage } from '../../companion/lifecycle';
import { reachedStages, useSurpriseRestricted } from '../../companion/previewAccess';

// Children keep the generic stages and thresholds; a form name appears only
// once that exact appearance reached the stage (revealedStages, or this
// creature's own server-confirmed stages).
export default function PetEvolutionGuide({ species, potion, creature, kind = 'pet', currentStage, revealedStages }) {
  const restricted = useSurpriseRestricted();
  const family = species || creature?.species;
  if (!family) return null;
  const current = currentStage === 'egg' ? 'egg' : companionStage(creature, kind);
  const revealed = restricted ? new Set(['egg', ...(revealedStages || reachedStages(creature, kind))]) : null;
  return (
    <ol aria-label="Pet growth stages" className="grid grid-cols-2 lg:grid-cols-4 gap-2">
      {companionLifecycle(family, potion || creature?.potion).map(({ id, label, form, description }) => {
        const shownForm = form && (!revealed || revealed.has(id)) ? form : null;
        return (
          <li key={id} aria-current={id === current ? 'step' : undefined}
            className={`rounded-xl border p-3 ${id === current ? 'border-sheikah-teal-deep bg-sheikah-teal/10' : 'border-ink-page-shadow bg-ink-page-aged'}`}>
            <div className="text-body font-semibold text-ink-primary">{label}{shownForm ? ` · ${shownForm}` : ''}</div>
            <p className="text-caption text-ink-secondary">{description}</p>
          </li>
        );
      })}
    </ol>
  );
}
