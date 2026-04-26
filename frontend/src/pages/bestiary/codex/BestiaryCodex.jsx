import { useState } from 'react';
import { motion } from 'framer-motion';
import { getPetCodex } from '../../../api';
import { useApi } from '../../../hooks/useApi';
import Loader from '../../../components/Loader';
import EmptyState from '../../../components/EmptyState';
import RuneBadge from '../../../components/journal/RuneBadge';
import { DragonIcon } from '../../../components/icons/JournalIcons';
import { staggerChildren, staggerItem } from '../../../motion/variants';
import SpeciesTile from './SpeciesTile';
import SpeciesDetailSheet from './SpeciesDetailSheet';

/**
 * Codex tab — illuminated browser of every authored species. Discovered
 * tiles show full sprite + lore + mount-collected pip strand; un-
 * discovered tiles render as locked silhouettes. Tile click opens a
 * BottomSheet with lore + per-potion evolution row.
 */
export default function BestiaryCodex() {
  const { data, loading } = useApi(getPetCodex);
  const [selected, setSelected] = useState(null);

  if (loading) return <Loader />;

  const species = data?.species || [];
  const potions = data?.potions || [];
  const totals = data?.totals || {};
  const totalPotions = potions.length;

  return (
    <div className="space-y-6">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base">
          the codex · every creature in these notebooks
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Codex
        </h1>
        <div className="font-script text-sm text-ink-whisper mt-1 max-w-xl">
          tap a tile for lore and the full evolution row · undiscovered species stay silhouetted until you hatch one
        </div>
      </header>

      <div className="flex gap-2 flex-wrap">
        <RuneBadge tone="teal" size="md">
          species {totals.discovered_species ?? 0}/{totals.species ?? species.length}
        </RuneBadge>
        <RuneBadge tone="gold" size="md">
          mounts {totals.mounts_owned ?? 0}/{totals.mounts_possible ?? 0}
        </RuneBadge>
      </div>

      {species.length === 0 ? (
        <EmptyState icon={<DragonIcon size={36} />}>
          The codex is empty — no species have been authored yet.
        </EmptyState>
      ) : (
        <motion.div
          variants={staggerChildren}
          initial="initial"
          animate="animate"
          className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3"
        >
          {species.map((s) => (
            <motion.div key={s.id} variants={staggerItem}>
              <SpeciesTile
                species={s}
                totalPotions={totalPotions}
                onSelect={setSelected}
              />
            </motion.div>
          ))}
        </motion.div>
      )}

      {selected && (
        <SpeciesDetailSheet
          species={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
