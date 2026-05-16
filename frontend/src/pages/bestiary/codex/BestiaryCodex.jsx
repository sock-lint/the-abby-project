import { useMemo, useState } from 'react';
import { getPetCodex } from '../../../api';
import { useApi } from '../../../hooks/useApi';
import Loader from '../../../components/Loader';
import EmptyState from '../../../components/EmptyState';
import IncipitBand from '../../../components/atlas/IncipitBand';
import TomeShelf from '../../../components/atlas/TomeShelf';
import { tierForProgress } from '../../../components/atlas/mastery.constants';
import { DragonIcon } from '../../../components/icons/JournalIcons';
import BestiaryFolio from './BestiaryFolio';
import SpeciesDetailSheet from './SpeciesDetailSheet';
import { groupSpeciesByChapter, totalRarityCounts } from './codex.constants';

const STORAGE_KEY = 'bestiary:codex:active-chapter';

/**
 * BestiaryCodex — illuminated codex of every authored species. The shelf
 * carries one tome per chapter (Mythic / Bonded / Hatched / Silhouettes);
 * the active chapter renders a BestiaryFolio with rubric, drop-cap, rarity
 * strand, and the existing SpeciesTile grid. Mirrors SigilCodex's structure
 * so the Atlas and Bestiary hubs speak the same vocabulary.
 */
export default function BestiaryCodex() {
  const { data, loading } = useApi(getPetCodex);
  const [selected, setSelected] = useState(null);

  // User-clicked chapter override. Persists across renders without a
  // setState-in-effect — we derive the effective active id on render.
  const [override, setOverride] = useState(() => {
    try {
      return window.localStorage?.getItem(STORAGE_KEY) || null;
    } catch {
      return null;
    }
  });

  const species = useMemo(() => data?.species || [], [data]);
  const potions = useMemo(() => data?.potions || [], [data]);
  const totals = data?.totals || {};
  const totalPotions = potions.length;

  const grouped = useMemo(() => groupSpeciesByChapter(species), [species]);

  const activeChapterId = useMemo(() => {
    if (override && grouped.some((c) => c.chapter.id === override)) return override;
    // Priority 1: a chapter the kid has progress in.
    const withProgress = grouped.find((c) => c.count > 0 && c.chapter.id !== 'silhouettes');
    if (withProgress) return withProgress.chapter.id;
    // Priority 2: any non-empty chapter.
    const nonEmpty = grouped.find((c) => c.count > 0);
    if (nonEmpty) return nonEmpty.chapter.id;
    return grouped[0]?.chapter.id ?? null;
  }, [override, grouped]);

  const setActiveChapterId = (id) => {
    setOverride(id);
    try {
      window.localStorage?.setItem(STORAGE_KEY, id);
    } catch {
      // ignore quota / disabled storage
    }
  };

  if (loading) return <Loader />;

  if (species.length === 0) {
    return (
      <EmptyState icon={<DragonIcon size={36} />}>
        The codex is empty — no species have been authored yet.
      </EmptyState>
    );
  }

  const discoveredSpecies = totals.discovered_species ?? 0;
  const totalSpecies = totals.species ?? species.length;
  const overallRarity = totalRarityCounts(species);
  const overallProgress = totalSpecies ? (discoveredSpecies / totalSpecies) * 100 : 0;

  const shelfItems = grouped.map(({ chapter, count, earned, total }) => {
    const pct = total ? (earned / total) * 100 : 0;
    const tier = tierForProgress({
      unlocked: count > 0,
      progressPct: pct,
      level: 0,
    });
    return {
      id: chapter.id,
      name: chapter.name,
      icon: chapter.letter,
      chip: `${count}`,
      progressPct: count > 0 ? pct : null,
      tier,
      ariaLabel: `${chapter.name}, ${count} ${count === 1 ? 'creature' : 'creatures'}`,
    };
  });

  const activeChapter = grouped.find((c) => c.chapter.id === activeChapterId) ?? grouped[0];

  return (
    <div className="space-y-5">
      <IncipitBand
        letter="B"
        title="Codex"
        kicker="· the codex of every creature ·"
        meta={
          <>
            <span className="tabular-nums">{discoveredSpecies} of {totalSpecies}</span>
            <span>discovered</span>
          </>
        }
        progressPct={overallProgress}
        rarityCounts={overallRarity}
      />

      <p className="font-script text-sm text-ink-whisper -mt-2 max-w-xl">
        tap a tile for lore and the full evolution row · undiscovered species stay silhouetted until you hatch one
      </p>

      <TomeShelf
        items={shelfItems}
        activeId={activeChapterId}
        onSelect={setActiveChapterId}
        ariaLabel="Bestiary codex chapters"
      />

      {activeChapter && (
        <BestiaryFolio
          chapter={activeChapter.chapter}
          species={activeChapter.species}
          earned={activeChapter.earned}
          total={activeChapter.total}
          rarityCounts={activeChapter.rarityCounts}
          totalPotions={totalPotions}
          onSelect={setSelected}
        />
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
