import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Map as MapIcon, X } from 'lucide-react';
import IconButton from './IconButton';
import RpgSprite from './rpg/RpgSprite';
import { useExpeditionToasts } from '../hooks/useExpeditionToasts';

/**
 * ExpeditionToastStack — soft slide-in nudge when one or more mounts
 * have returned from their expedition and have unclaimed loot waiting.
 *
 * Mirrors CompanionGrowthToastStack visually but doesn't escalate to a
 * modal — claiming is a deliberate action that happens on the Mounts
 * page (where the kid can see what they got). The toast deep-links there.
 */
export default function ExpeditionToastStack() {
  const { ready, dismiss } = useExpeditionToasts();
  const navigate = useNavigate();

  return (
    <div className="fixed top-32 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none">
      <AnimatePresence>
        {ready.map((expedition) => (
          <motion.div
            key={expedition.id}
            layout
            initial={{ x: 300, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: 300, opacity: 0 }}
            className="pointer-events-auto flex items-center gap-3 rounded-lg border border-gold-leaf/60 bg-gold-leaf/15 px-3 py-2 shadow-lg cursor-pointer"
            onClick={() => navigate('/bestiary?tab=mounts')}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                navigate('/bestiary?tab=mounts');
              }
            }}
            aria-label={`${expedition.species_name} returned — claim loot on Mounts`}
          >
            <MapIcon size={18} className="text-gold-leaf shrink-0" aria-hidden="true" />
            <RpgSprite
              spriteKey={expedition.species_sprite_key ? `${expedition.species_sprite_key}-mount` : null}
              fallbackSpriteKey={expedition.species_sprite_key}
              icon={expedition.species_icon || '🐾'}
              size={32}
              alt={expedition.species_name}
              potionSlug={expedition.potion_slug}
            />
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-ink-primary">
                {expedition.species_name} is back
              </div>
              <div className="text-micro text-ink-whisper">
                tap to claim · {expedition.tier} expedition
              </div>
            </div>
            <IconButton
              variant="ghost"
              size="sm"
              aria-label="Dismiss notification"
              className="text-ink-secondary shrink-0"
              onClick={(e) => {
                e.stopPropagation();
                dismiss(expedition.id);
              }}
            >
              <X size={14} />
            </IconButton>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
