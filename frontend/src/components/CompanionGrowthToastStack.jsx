import { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sprout, X } from 'lucide-react';
import { useCompanionGrowthToasts } from '../hooks/useCompanionGrowthToasts';
import IconButton from './IconButton';
import RpgSprite from './rpg/RpgSprite';
import PetCeremonyModal from '../pages/bestiary/PetCeremonyModal';

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
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(event._toastId), 5000);
    return () => clearTimeout(timer);
  }, [event._toastId, onDismiss]);

  return (
    <motion.div
      layout
      initial={{ x: 300, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 300, opacity: 0 }}
      className="flex items-center gap-3 rounded-lg border border-moss/60 bg-moss/15 px-3 py-2 shadow-lg"
    >
      <Sprout size={18} className="text-moss shrink-0" aria-hidden="true" />
      <RpgSprite
        spriteKey={event.species_sprite_key}
        icon={event.species_icon || '🐾'}
        size={32}
        alt={event.species_name}
        potionSlug={event.potion_slug}
      />
      <div className="flex-1 min-w-0">
        <div className="text-xs font-medium text-ink-primary">
          {event.potion_name} {event.species_name} grew
        </div>
        <div className="text-micro text-ink-whisper">
          +{event.growth_added} · {event.new_growth}/100
        </div>
      </div>
      <IconButton
        onClick={() => onDismiss(event._toastId)}
        variant="ghost"
        size="sm"
        aria-label="Dismiss notification"
        className="text-ink-secondary shrink-0"
      >
        <X size={14} />
      </IconButton>
    </motion.div>
  );
}

export default function CompanionGrowthToastStack() {
  const { events, dismiss } = useCompanionGrowthToasts();

  // Split is purely derived — tick events become toasts, the first
  // pending evolved event escalates to the full celebration modal. The
  // modal's onDismiss clears that one event from the underlying list.
  // No setState-in-effect dance, no separate evolve queue.
  const tickToasts = events.filter((e) => !e.evolved);
  const activeEvolve = events.find((e) => e.evolved) || null;

  return (
    <>
      <div className="fixed top-20 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none">
        <AnimatePresence>
          {tickToasts.map((event) => (
            <div key={event._toastId} className="pointer-events-auto">
              <GrowthToast event={event} onDismiss={dismiss} />
            </div>
          ))}
        </AnimatePresence>
      </div>
      {activeEvolve && (
        <PetCeremonyModal
          mode="evolve"
          species={{
            name: activeEvolve.species_name,
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
