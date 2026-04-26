import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Crown } from 'lucide-react';
import { getStable, activateMount } from '../../../api';
import { useApi } from '../../../hooks/useApi';
import Loader from '../../../components/Loader';
import EmptyState from '../../../components/EmptyState';
import ErrorAlert from '../../../components/ErrorAlert';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import RuneBadge from '../../../components/journal/RuneBadge';
import DeckleDivider from '../../../components/journal/DeckleDivider';
import { DragonIcon } from '../../../components/icons/JournalIcons';
import RpgSprite from '../../../components/rpg/RpgSprite';
import { RARITY_TEXT_COLORS } from '../../../constants/colors';
import {
  MOUNT_FILTERS,
  compareByRarityThenName,
  daysUntilReady,
} from './party.constants';

/**
 * Mounts — owned, evolved companions you can ride. Lifted from the old
 * Stable.jsx "mounts" branch and given filter pills (All / Active /
 * Ready to breed / On cooldown). Cooldown info is computed from the
 * `last_bred_at` field added to UserMountSerializer.
 */
export default function Mounts() {
  const { data: stableData, loading, reload } = useApi(getStable);
  const [filter, setFilter] = useState('all');
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);

  const mounts = useMemo(() => stableData?.mounts || [], [stableData]);
  const totalPossible = stableData?.total_possible || 0;

  const counts = useMemo(() => {
    const out = {};
    MOUNT_FILTERS.forEach((f) => {
      out[f.key] = mounts.filter(f.match).length;
    });
    return out;
  }, [mounts]);

  const visibleMounts = useMemo(() => {
    const f = MOUNT_FILTERS.find((x) => x.key === filter) || MOUNT_FILTERS[0];
    return [...mounts.filter(f.match)].sort(compareByRarityThenName);
  }, [mounts, filter]);

  if (loading) return <Loader />;

  const handleActivateMount = async (mountId) => {
    setWorking(true);
    setError('');
    try { await activateMount(mountId); reload(); }
    catch (e) { setError(e.message); }
    finally { setWorking(false); }
  };

  return (
    <div className="space-y-6">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base">
          your party · mounts you can ride
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Mounts
        </h1>
        <div className="font-script text-sm text-ink-whisper mt-1 max-w-xl">
          companions that bloomed past growth 100 evolve into mounts · pair two on the Hatchery tab to breed a hybrid egg
        </div>
      </header>

      <ErrorAlert message={error} />

      <div className="flex gap-2 flex-wrap">
        <RuneBadge tone="gold" size="md">
          mounts {mounts.length}/{totalPossible}
        </RuneBadge>
      </div>

      {mounts.length > 0 && (
        <div
          role="tablist"
          aria-label="Filter mounts"
          className="flex flex-wrap gap-1 bg-ink-page-aged rounded-lg p-1 border border-ink-page-shadow"
        >
          {MOUNT_FILTERS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={filter === key}
              onClick={() => setFilter(key)}
              disabled={counts[key] === 0 && key !== 'all'}
              className={`flex-1 min-w-[5rem] px-3 py-1.5 rounded-md font-display text-sm transition-colors disabled:opacity-40 ${
                filter === key
                  ? 'bg-sheikah-teal-deep text-ink-page-rune-glow'
                  : 'text-ink-secondary hover:text-ink-primary'
              }`}
            >
              {label} <span className="opacity-70">({counts[key]})</span>
            </button>
          ))}
        </div>
      )}

      {mounts.length === 0 ? (
        <>
          <DeckleDivider glyph="dragon-crest" />
          <EmptyState icon={<DragonIcon size={36} />}>
            No mounts yet. Grow a companion to 100 to evolve it into a mount.
          </EmptyState>
        </>
      ) : visibleMounts.length === 0 ? (
        <EmptyState icon={<DragonIcon size={28} />}>
          No mounts match this filter.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {visibleMounts.map((mount) => {
            const cooldownDaysLeft = daysUntilReady(mount.last_bred_at);
            return (
              <motion.div key={mount.id} whileHover={{ y: -2 }}>
                <ParchmentCard
                  className={`text-center cursor-pointer transition-all ${
                    mount.is_active
                      ? 'ring-2 ring-offset-2 ring-offset-ink-page ring-gold-leaf'
                      : ''
                  }`}
                >
                  <div className="flex items-center justify-center h-16 mb-1">
                    <RpgSprite
                      spriteKey={`${mount.species.sprite_key}-mount`}
                      fallbackSpriteKey={mount.species.sprite_key}
                      icon={mount.species.icon}
                      size={64}
                      alt={`${mount.potion.name} ${mount.species.name}`}
                      potionSlug={mount.potion.slug}
                    />
                  </div>
                  <div className="font-body text-sm font-medium leading-tight">
                    {mount.potion.name} {mount.species.name}
                  </div>
                  <div
                    className={`font-script text-tiny uppercase tracking-wider ${
                      RARITY_TEXT_COLORS[mount.potion.rarity]
                    }`}
                  >
                    {mount.potion.rarity}
                  </div>
                  <div className="font-script text-tiny text-gold-leaf mt-1">mount</div>
                  {cooldownDaysLeft !== null ? (
                    <div className="mt-1 font-script text-tiny text-ink-whisper">
                      resting · {cooldownDaysLeft}d
                    </div>
                  ) : (
                    <div className="mt-1 font-script text-tiny text-moss">
                      ready to breed
                    </div>
                  )}
                  {mount.is_active ? (
                    <div className="mt-1 font-script text-tiny text-gold-leaf flex items-center justify-center gap-1">
                      <Crown size={10} /> riding
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleActivateMount(mount.id)}
                      disabled={working}
                      className="mt-2 w-full font-body text-xs py-1.5 rounded-lg bg-gold-leaf/20 text-ember-deep border border-gold-leaf/60 hover:bg-gold-leaf/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {working ? 'Saddling…' : 'Saddle up'}
                    </button>
                  )}
                </ParchmentCard>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
