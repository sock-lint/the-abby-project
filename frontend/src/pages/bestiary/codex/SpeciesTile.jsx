import { motion } from 'framer-motion';
import { Lock } from 'lucide-react';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import RpgSprite from '../../../components/rpg/RpgSprite';
import { loreOneLiner } from './bestiary.constants';

/**
 * Single tile in the Codex grid. Discovered species show their sprite +
 * lore preview + a mounts-collected pip strand. Un-discovered species
 * render as a debossed silhouette intaglio with a lock chip — same
 * visual vocabulary as the Reliquary Codex's locked sigils.
 */
export default function SpeciesTile({ species, totalPotions, onSelect }) {
  const owned = species.owned_mount_potion_ids?.length || 0;
  const discovered = !!species.discovered;

  if (!discovered) {
    return (
      <button
        type="button"
        onClick={() => onSelect(species)}
        aria-label={`Unknown species — not yet discovered`}
        className="block w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep rounded-2xl"
      >
        <ParchmentCard className="text-center cursor-pointer transition-all opacity-70 hover:opacity-100">
          <div className="flex items-center justify-center h-14 mb-1">
            <span
              aria-hidden="true"
              style={{ filter: 'brightness(0)' }}
              className="text-4xl"
            >
              {species.icon || '❓'}
            </span>
          </div>
          <div className="font-display text-sm text-ink-secondary leading-tight">
            ???
          </div>
          <div className="font-script text-tiny text-ink-whisper mt-1 inline-flex items-center gap-1">
            <Lock size={10} aria-hidden="true" />
            hatch one to discover
          </div>
        </ParchmentCard>
      </button>
    );
  }

  return (
    <motion.button
      type="button"
      whileHover={{ y: -2 }}
      onClick={() => onSelect(species)}
      aria-label={`${species.name} — ${owned} of ${totalPotions} mounts collected`}
      className="block w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep rounded-2xl"
    >
      <ParchmentCard className="text-center cursor-pointer transition-all">
        <div className="flex items-center justify-center h-14 mb-1">
          <RpgSprite
            spriteKey={species.sprite_key}
            icon={species.icon}
            size={56}
            alt={species.name}
          />
        </div>
        <div className="font-display text-sm text-ink-primary font-medium leading-tight">
          {species.name}
        </div>
        <div className="font-script text-micro text-ink-whisper mt-1 line-clamp-2 min-h-[1.6em]">
          {loreOneLiner(species.description) || ' '}
        </div>
        <PotionStrand owned={owned} total={totalPotions} />
      </ParchmentCard>
    </motion.button>
  );
}

function PotionStrand({ owned, total }) {
  if (!total) return null;
  const pips = Array.from({ length: total }, (_, i) => i < owned);
  return (
    <div
      className="mt-2 flex justify-center gap-0.5"
      role="img"
      aria-label={`${owned} of ${total} mount variants collected`}
    >
      {pips.map((filled, i) => (
        <span
          key={i}
          aria-hidden="true"
          className={`block w-2 h-2 rounded-full ${
            filled ? 'bg-gold-leaf' : 'bg-ink-page-shadow/60'
          }`}
        />
      ))}
    </div>
  );
}
