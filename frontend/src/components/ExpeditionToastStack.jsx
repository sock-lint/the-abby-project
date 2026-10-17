import { useNavigate } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { Map as MapIcon } from 'lucide-react';
import NotificationToast from './NotificationToast';
import RpgSprite from './rpg/RpgSprite';
import { useExpeditionToasts } from '../hooks/useExpeditionToasts';
import { birdFormName } from '../companion/birdEvolution';

/**
 * ExpeditionToastStack — soft slide-in nudge when one or more mounts
 * have returned from their expedition and have unclaimed loot waiting.
 *
 * Mirrors CompanionGrowthToastStack visually but doesn't escalate to a
 * modal — claiming is a deliberate action that happens on the Mounts
 * page (where the kid can see what they got). The toast deep-links there.
 */
export default function ExpeditionToastStack({ inline = false }) {
  const { ready, dismiss } = useExpeditionToasts();
  const navigate = useNavigate();

  const items = (
    <AnimatePresence>
      {ready.map((expedition) => {
        const name = birdFormName(
          { name: expedition.species_name, slug: expedition.species_slug, sprite_key: expedition.species_sprite_key },
          { slug: expedition.potion_slug }, 'bird');
        return (
        <NotificationToast
            key={expedition.id}
            tone="treasure"
            onDismiss={() => dismiss(expedition.id)}
            className="pointer-events-auto cursor-pointer"
            onClick={() => navigate('/bestiary?tab=mounts')}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              // The nested dismiss button owns its own Enter/Space activation.
              if (e.target !== e.currentTarget) return;
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                navigate('/bestiary?tab=mounts');
              }
            }}
            aria-label={`${name} returned — claim rewards on Grown pets`}
          >
            <MapIcon size={18} className="text-current shrink-0" aria-hidden="true" />
            <RpgSprite
              spriteKey={expedition.species_sprite_key ? `${expedition.species_sprite_key}-mount` : null}
              fallbackSpriteKey={expedition.species_sprite_key}
              icon={expedition.species_icon || '🐾'}
              size={32}
              alt={name}
              potionSlug={expedition.potion_slug}
            />
            <div className="flex-1 min-w-0">
              <div className="text-caption font-medium text-current">
                {name} is back
              </div>
              <div className="text-caption text-current">
                tap to claim · {expedition.tier} expedition
              </div>
            </div>
          </NotificationToast>
        ); })}
      </AnimatePresence>
  );

  if (inline) return items;
  return (
    <div className="fixed top-32 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none" aria-live="polite" aria-atomic="false">
      {items}
    </div>
  );
}
