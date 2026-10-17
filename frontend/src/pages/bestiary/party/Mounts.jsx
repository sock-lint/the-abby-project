import { useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  getStable, activateMount, claimExpedition,
} from '../../../api';
import { useApi } from '../../../hooks/useApi';
import Loader from '../../../components/Loader';
import EmptyState from '../../../components/EmptyState';
import ErrorAlert from '../../../components/ErrorAlert';
import Button from '../../../components/Button';
import IncipitBand from '../../../components/atlas/IncipitBand';
import TomeShelf from '../../../components/atlas/TomeShelf';
import DeckleDivider from '../../../components/journal/DeckleDivider';
import { DragonIcon } from '../../../components/icons/JournalIcons';
import { PROGRESS_TIER } from '../../../components/atlas/mastery.constants';
import PetCeremonyModal from '../PetCeremonyModal';
import ExpeditionLaunchSheet from './ExpeditionLaunchSheet';
import CompanionPreview from '../../../components/companion/CompanionPreview';
import { birdFormName } from '../../../companion/birdEvolution';
import OwnedMountGrid from './OwnedMountGrid';
import { isCatalogAvailable } from '../../../utils/catalogAvailability';
import DailyExpeditionCard from './DailyExpeditionCard';
import useExpeditionRefresh from './useExpeditionRefresh';
import usePetMutationGuard from './usePetMutationGuard';
import {
  MOUNT_FILTERS,
  compareByRarityThenName,
} from './party.constants';

/**
 * Mounts — owned, evolved companions you can ride. Lifted from the old
 * Stable.jsx "mounts" branch and given filter pills (All / Active /
 * Ready to breed / On cooldown). Cooldown info is computed from the
 * `last_bred_at` field added to UserMountSerializer.
 */
export default function Mounts() {
  const { data: stableData, loading, error: stableError, reload } = useApi(getStable);
  const [filter, setFilter] = useState('all');
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const [launchMount, setLaunchMount] = useState(null);
  const [claimedExpedition, setClaimedExpedition] = useState(null);
  const [previewId, setPreviewId] = useState(null);
  const [reaction, setReaction] = useState(null);
  const receiptCounter = useRef(0);
  const beginMutation = usePetMutationGuard();
  const [searchParams] = useSearchParams();

  const mounts = useMemo(() => stableData?.mounts || [], [stableData]);
  useExpeditionRefresh(mounts, reload);
  const supportedMounts = useMemo(() => mounts.filter(isCatalogAvailable), [mounts]);
  const savedMounts = mounts.filter((mount) => !isCatalogAvailable(mount));
  const totalPossible = stableData?.total_possible || 0;

  const counts = useMemo(() => {
    const out = {};
    MOUNT_FILTERS.forEach((f) => {
      out[f.key] = supportedMounts.filter(f.match).length;
    });
    return out;
  }, [supportedMounts]);

  const visibleMounts = useMemo(() => {
    const f = MOUNT_FILTERS.find((x) => x.key === filter) || MOUNT_FILTERS[0];
    return [...supportedMounts.filter(f.match)].sort(compareByRarityThenName);
  }, [supportedMounts, filter]);
  const requestedId = Number(searchParams.get('mount'));
  const homeMount = supportedMounts.find((mount) => mount.id === previewId)
    || supportedMounts.find((mount) => mount.id === requestedId) || supportedMounts.find((mount) => mount.is_active) || supportedMounts[0];
  const companionName = homeMount?.species.id != null && homeMount?.potion.id != null
    ? stableData?.pets?.find((pet) => pet.species.id === homeMount.species.id && pet.potion.id === homeMount.potion.id)?.name?.trim() : null;
  const homeCreature = companionName ? { ...homeMount, name: companionName } : homeMount;

  if (loading) return <Loader />;

  if (stableError && !stableData) {
    return (
      <div className="space-y-3 max-w-xl mx-auto">
        <ErrorAlert message={stableError} />
        <Button variant="secondary" size="sm" onClick={reload}>
          Try again
        </Button>
      </div>
    );
  }

  const handleActivateMount = async (mountId) => {
    const request = beginMutation();
    if (!request) return;
    setWorking(true);
    setError('');
    try { await activateMount(mountId); if (request.isCurrent()) reload(); }
    catch (e) { if (request.isCurrent()) setError(e.message); }
    finally { if (request.isCurrent()) setWorking(false); request.finish(); }
  };

  const handleClaim = async (expeditionId) => {
    const request = beginMutation();
    if (!request) return;
    setWorking(true);
    setError('');
    try {
      const result = await claimExpedition(expeditionId);
      if (!request.isCurrent()) return;
      if (result.freshly_claimed === true) {
        setClaimedExpedition(result);
        if (result.mount?.id === homeMount?.id) setReaction({ id: ++receiptCounter.current, creatureId: result.mount.id, action: 'celebrate' });
      }
      reload();
    } catch (e) {
      if (request.isCurrent()) setError(e.message || 'Could not claim expedition.');
    } finally {
      if (request.isCurrent()) setWorking(false);
      request.finish();
    }
  };

  return (
    <div className="space-y-6">
      {homeMount && <CompanionPreview
        variant="primary"
        kind="mount"
        creature={homeCreature}
        kicker="At home in your woodland"
        summary="Play together, then choose a little adventure for today."
        reaction={reaction?.creatureId === homeMount.id ? reaction : null}
      >
        <DailyExpeditionCard mount={homeMount} name={companionName || birdFormName(homeMount.species, homeMount.potion, 'bird')} working={working} onLaunch={setLaunchMount} onClaim={handleClaim} onRefresh={reload} />
      </CompanionPreview>}
      <IncipitBand
        letter="M"
        title="Grown pets"
        kicker="Your evolved companions"
        meta={
          <>
            <span className="tabular-nums">{supportedMounts.length} of {totalPossible}</span>
            <span>evolved</span>
          </>
        }
        progressPct={totalPossible ? (supportedMounts.length / totalPossible) * 100 : 0}
      />

      <p className="font-script text-body text-ink-whisper -mt-2 max-w-xl">
        Chick becomes Fledgling at 50 growth, then Bird at 100 growth. Send them exploring and collect their finds when they return.
      </p>

      <ErrorAlert message={error || stableError} />

      {supportedMounts.length > 0 && (
        <TomeShelf
          ariaLabel="Filter mounts"
          activeId={filter}
          onSelect={setFilter}
          items={MOUNT_FILTERS
            .filter(({ key }) => key === 'all' || counts[key] > 0)
            .map(({ key, label, icon }) => ({
              id: key,
              name: label,
              icon,
              chip: `×${counts[key]}`,
              progressPct: null,
              tier: PROGRESS_TIER.nascent,
              variant: 'vessel',
              ariaLabel: `${label} (${counts[key]})`,
            }))}
        />
      )}

      {supportedMounts.length === 0 ? (
        <>
          <DeckleDivider glyph="dragon-crest" />
          <EmptyState icon={<DragonIcon size={36} />}>
            {savedMounts.length ? 'Your earlier grown pets keep their expeditions in Saved collection below.' : 'No grown pets yet. Feed a companion to help it reach 100 growth.'}
          </EmptyState>
        </>
      ) : visibleMounts.length === 0 ? (
        <EmptyState icon={<DragonIcon size={28} />}>
          No grown pets match this filter.
        </EmptyState>
      ) : (
        <OwnedMountGrid mounts={visibleMounts} working={working} onActivate={handleActivateMount} onPreview={(id) => { setReaction(null); setPreviewId(id); }} onClaim={handleClaim} onLaunch={setLaunchMount} />
      )}

      {savedMounts.length > 0 && <section className="space-y-3" aria-label="Saved collection">
        <div><h2 className="font-body font-bold text-lede text-ink-primary">Saved collection</h2>
          <p className="font-body text-caption text-ink-secondary">{savedMounts.length} earlier grown {savedMounts.length === 1 ? 'pet' : 'pets'}. Their progress and expeditions stay available.</p></div>
        <OwnedMountGrid mounts={savedMounts} working={working} onActivate={handleActivateMount} onClaim={handleClaim} onLaunch={setLaunchMount} label="Saved grown pets" />
      </section>}
      {launchMount && (
        <ExpeditionLaunchSheet
          mount={launchMount}
          onDismiss={() => setLaunchMount(null)}
          onLaunched={() => reload()}
        />
      )}
      {claimedExpedition && (
        <PetCeremonyModal
          mode="expedition_return"
          expedition={claimedExpedition}
          onDismiss={() => setClaimedExpedition(null)}
        />
      )}
    </div>
  );
}
