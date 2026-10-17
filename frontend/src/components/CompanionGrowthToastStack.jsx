import { useEffect } from 'react';
import { AnimatePresence } from 'framer-motion';
import { Sprout } from 'lucide-react';
import { useCompanionGrowthToasts } from '../hooks/useCompanionGrowthToasts';
import NotificationToast from './NotificationToast';
import { TOAST_DURATION_STANDARD } from '../constants/timing';
import RpgSprite from './rpg/RpgSprite';
import PetCeremonyModal from '../pages/bestiary/PetCeremonyModal';
import { companionFormName, lifecycleStageLabel } from '../companion/lifecycle';

/**
 * Surfaces silent companion auto-growth events as a slide-in toast strip
 * (sibling of DropToastStack). Each event is the +N growth tick that
 * happens once per day on the user's first activity. If a tick pushed a
 * companion past evolution threshold the toast escalates into the full
 * PetCeremonyModal evolve sequence — same visual cohort as the explicit
 * feed-evolve flow.
 *
 * Tick toasts auto-dismiss after 5s. The escalated evolve modal needs an
 * explicit Continue dismiss.
 */
function GrowthToast({ event, onDismiss }) {
  const form = companionFormName(
    { name: event.species_name, slug: event.species_slug, sprite_key: event.species_sprite_key },
    { slug: event.potion_slug }, event.lifecycle_stage);
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(event._toastId), TOAST_DURATION_STANDARD);
    return () => clearTimeout(timer);
  }, [event._toastId, onDismiss]);

  return (
    <NotificationToast
      tone="growth"
      onDismiss={() => onDismiss(event._toastId)}
    >
      <Sprout size={18} className="text-current shrink-0" aria-hidden="true" />
      <RpgSprite
        spriteKey={event.species_sprite_key}
        icon={event.species_icon || '🐾'}
        size={32}
        alt={form}
        potionSlug={event.potion_slug}
      />
      <div className="flex-1 min-w-0">
        <div className="text-caption font-medium text-current">
          {event.potion_name} {form} grew
        </div>
        <div className="text-caption text-current">
          +{event.growth_added} · {event.new_growth}/100{lifecycleStageLabel(event.lifecycle_stage) ? ` · ${lifecycleStageLabel(event.lifecycle_stage)} stage` : ''}
        </div>
      </div>
    </NotificationToast>
  );
}

export default function CompanionGrowthToastStack({ inline = false }) {
  const { events, dismiss } = useCompanionGrowthToasts();

  const tickToasts = events.filter((e) => !e.evolved);
  const activeEvolve = events.find((e) => e.evolved) || null;

  const items = (
    <AnimatePresence>
      {tickToasts.map((event) => (
        <div key={event._toastId} className="pointer-events-auto">
          <GrowthToast event={event} onDismiss={dismiss} />
        </div>
      ))}
    </AnimatePresence>
  );

  return (
    <>
      {inline ? items : (
        <div className="fixed top-20 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none" aria-live="polite" aria-atomic="false">
          {items}
        </div>
      )}
      {activeEvolve && (
        <PetCeremonyModal
          mode="evolve"
          species={{
            name: activeEvolve.species_name,
            slug: activeEvolve.species_slug,
            sprite_key: activeEvolve.species_sprite_key,
            icon: activeEvolve.species_icon,
          }}
          potion={{
            name: activeEvolve.potion_name,
            slug: activeEvolve.potion_slug,
          }}
          onDismiss={() => dismiss(activeEvolve._toastId)}
        />
      )}
    </>
  );
}
