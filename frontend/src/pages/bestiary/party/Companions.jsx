import { useCallback, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { getStable, getInventory, feedPet, activatePet, claimExpedition } from '../../../api';
import { useApi } from '../../../hooks/useApi';
import Loader from '../../../components/Loader';
import EmptyState from '../../../components/EmptyState';
import ErrorAlert from '../../../components/ErrorAlert';
import Button from '../../../components/Button';
import BottomSheet from '../../../components/BottomSheet';
import IncipitBand from '../../../components/atlas/IncipitBand';
import TomeShelf from '../../../components/atlas/TomeShelf';
import { EggIcon } from '../../../components/icons/JournalIcons';
import CatalogIcon from '../../../components/rpg/CatalogIcon';
import { normalizeList } from '../../../utils/api';
import { PROGRESS_TIER } from '../../../components/atlas/mastery.constants';
import { COMPANION_FILTERS, compareByRarityThenName } from './party.constants';
import PetCeremonyModal from '../PetCeremonyModal';
import CompanionPreview from '../../../components/companion/CompanionPreview';
import { creatureLabel } from '../../../companion/appearance';
import { birdFormName, birdStage } from '../../../companion/birdEvolution';
import OwnedPetGrid from './OwnedPetGrid';
import { isCatalogAvailable } from '../../../utils/catalogAvailability';
import DailyExpeditionCard from './DailyExpeditionCard';
import ExpeditionLaunchSheet from './ExpeditionLaunchSheet';
import useExpeditionRefresh from './useExpeditionRefresh';
import usePetMutationGuard from './usePetMutationGuard';

/**
 * Companions — owned, unevolved pets. Lifted from the old Stable.jsx
 * "pets" branch and given filter pills (All / Active / Hungry / Ready
 * to evolve) so a roster of dozens stays navigable.
 */
export default function Companions() {
  const {
    data: stableData, loading: loadingStable, error: stableError, reload: reloadStable,
  } = useApi(getStable);
  const {
    data: inventoryData, loading: loadingInventory, error: inventoryError,
    reload: reloadInventory,
  } = useApi(getInventory);
  const [filter, setFilter] = useState('all');
  const [error, setError] = useState('');
  const [selectedPet, setSelectedPet] = useState(null);
  const [viewPetId, setViewPetId] = useState(null);
  const [working, setWorking] = useState(false);
  const [evolveCeremony, setEvolveCeremony] = useState(null);
  const [launchMount, setLaunchMount] = useState(null);
  const [claimedExpedition, setClaimedExpedition] = useState(null);
  const [reaction, setReaction] = useState(null);
  const presentation = useRef(null);
  const updatePresentation = useCallback((value) => { presentation.current = value; }, []);
  const receiptCounter = useRef(0);
  const beginMutation = usePetMutationGuard();

  const pets = useMemo(() => stableData?.pets || [], [stableData]);
  const mounts = useMemo(() => stableData?.mounts || [], [stableData]);
  useExpeditionRefresh(mounts, reloadStable);
  const supportedPets = useMemo(() => pets.filter(isCatalogAvailable), [pets]);
  const savedPets = pets.filter((pet) => !isCatalogAvailable(pet));
  const totalPossible = stableData?.total_possible || 0;
  const inventory = normalizeList(inventoryData);
  const foods = inventory.filter((e) => e.item.item_type === 'food' && e.quantity > 0);

  const counts = useMemo(() => {
    const out = {};
    COMPANION_FILTERS.forEach((f) => {
      out[f.key] = supportedPets.filter(f.match).length;
    });
    return out;
  }, [supportedPets]);

  const visiblePets = useMemo(() => {
    const f = COMPANION_FILTERS.find((x) => x.key === filter) || COMPANION_FILTERS[0];
    return [...supportedPets.filter(f.match)].sort(compareByRarityThenName);
  }, [supportedPets, filter]);
  const homePet = supportedPets.find((pet) => pet.id === viewPetId) || supportedPets.find((pet) => pet.is_active) || supportedPets[0];
  const homeMount = homePet?.evolved_to_mount && homePet.species.id != null && homePet.potion.id != null ? stableData?.mounts?.find((mount) =>
    mount.species.id === homePet.species.id && mount.potion.id === homePet.potion.id) : null;
  const explorePath = `/bestiary?tab=mounts${homeMount ? `&mount=${homeMount.id}` : ''}`;

  const carePet = pets.find((pet) => pet.id === selectedPet?.id);

  if (loadingStable || loadingInventory) return <Loader />;

  const refresh = () => { reloadStable(); reloadInventory(); };

  // A failed stable fetch used to render "No companions yet. Find eggs and
  // potions in drops…" — indistinguishable from an empty party, and the kid
  // has no way to retry.
  const fetchError = stableError || inventoryError;
  // Only the stable is load-bearing here: a failed satchel fetch just costs
  // the feed chips, so the party still renders with a banner over it.
  if (fetchError && !stableData) {
    return (
      <div className="space-y-3 max-w-xl mx-auto">
        <ErrorAlert message={fetchError} />
        <Button variant="secondary" size="sm" onClick={refresh}>
          Try again
        </Button>
      </div>
    );
  }

  const handleFeed = async (pet, foodItemId) => {
    const request = beginMutation();
    if (!request) return;
    setWorking(true);
    setError('');
    try {
      const result = await feedPet(pet.id, foodItemId);
      if (!request.isCurrent()) return;
      setSelectedPet(null);
      const currentPresentation = presentation.current?.creatureId === pet.id ? presentation.current : null;
      if (result?.evolved && !(currentPresentation?.sharedBirdReady && currentPresentation.evolutionMotionEnabled)) {
        setEvolveCeremony({ species: pet.species, potion: pet.potion, fromStage: birdStage(pet), reducedMotion: currentPresentation?.evolutionMotionEnabled === false });
      }
      const changedStage = (result?.lifecycle_stage && result.lifecycle_stage !== pet.lifecycle_stage)
        || (result?.evolution_stage && result.evolution_stage !== pet.evolution_stage);
      if (changedStage) setReaction(null);
      else if (!result?.evolved) setReaction({ id: ++receiptCounter.current, creatureId: pet.id, action: 'celebrate' });
      refresh();
    } catch (e) { if (request.isCurrent()) setError(e.message); }
    finally { if (request.isCurrent()) setWorking(false); request.finish(); }
  };

  const handleActivatePet = async (petId) => {
    const request = beginMutation();
    if (!request) return;
    setWorking(true);
    setError('');
    try { await activatePet(petId); if (request.isCurrent()) refresh(); }
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
        if (result.mount?.id === homeMount?.id) setReaction({ id: ++receiptCounter.current, creatureId: homePet.id, action: 'celebrate' });
      }
      refresh();
    } catch (e) { if (request.isCurrent()) setError(e.message); }
    finally { if (request.isCurrent()) setWorking(false); request.finish(); }
  };

  return (
    <div className="space-y-6">
      {evolveCeremony && (
        <PetCeremonyModal
          mode="evolve"
          species={evolveCeremony.species}
          potion={evolveCeremony.potion}
          fromStage={evolveCeremony.fromStage}
          reducedMotion={evolveCeremony.reducedMotion}
          onDismiss={() => setEvolveCeremony(null)}
        />
      )}
      {homePet && <CompanionPreview
        variant="primary"
        creature={homePet}
        kicker="At home in your woodland"
        summary={homePet.evolved_to_mount ? 'Play together, then choose a little adventure for today.' : 'Play together or choose a snack to help your companion grow.'}
        reaction={reaction?.creatureId === homePet.id ? reaction : null}
        onPresentationChange={updatePresentation}
      >
        <div className="companion-preview-actions">
          {!homePet.evolved_to_mount && <Button disabled={working} onClick={() => setSelectedPet(homePet)}>Feed your companion</Button>}
          {homePet.evolved_to_mount && !homeMount && <Link className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep" to={explorePath}>Visit grown pets →</Link>}
          <Link className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep" to="/bestiary?tab=hatchery">Hatch a pet →</Link>
        </div>
        {homeMount && <DailyExpeditionCard mount={homeMount} name={homePet.name?.trim() || birdFormName(homePet.species, homePet.potion, birdStage(homePet))} working={working} onLaunch={setLaunchMount} onClaim={handleClaim} onRefresh={reloadStable} />}
      </CompanionPreview>}

      {launchMount && <ExpeditionLaunchSheet mount={launchMount} onDismiss={() => setLaunchMount(null)} onLaunched={refresh} />}
      {claimedExpedition && <PetCeremonyModal mode="expedition_return" expedition={claimedExpedition} onDismiss={() => setClaimedExpedition(null)} />}

      <IncipitBand
        letter="C"
        title="Companions"
        kicker="The pets you've hatched"
        meta={
          <>
            <span className="tabular-nums">{supportedPets.length} of {totalPossible}</span>
            <span>hatched</span>
          </>
        }
        progressPct={totalPossible ? (supportedPets.length / totalPossible) * 100 : 0}
      />

      <p className="font-script text-body text-ink-whisper -mt-2 max-w-xl">
        Every companion starts as an egg. Hatch a baby, help it reach its middle stage at 50 growth, then its grown form at 100 growth, ready to explore.
      </p>

      {/* Covers the partial case too: stable loaded but the satchel fetch
          failed, which would otherwise just hide the feed chips. */}
      <ErrorAlert message={error || fetchError} />

      {supportedPets.length > 0 && (
        <TomeShelf
          ariaLabel="Filter companions"
          activeId={filter}
          onSelect={setFilter}
          items={COMPANION_FILTERS
            // Drop empty buckets except "all" (matches Sketchbook).
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

      {supportedPets.length === 0 ? (
        <EmptyState icon={<EggIcon size={36} />}>
          {savedPets.length ? 'Your earlier pets are in Saved collection below. Use an available egg and potion to hatch a new companion.' : 'No companions yet. Collect an egg and a potion, then combine them on the Hatching tab.'}
        </EmptyState>
      ) : visiblePets.length === 0 ? (
        <EmptyState icon={<EggIcon size={28} />}>
          No companions match this filter.
        </EmptyState>
      ) : (
        <OwnedPetGrid pets={visiblePets} selectedPetId={selectedPet?.id} onSelect={(pet) => { setReaction(null); setViewPetId(pet.id); setSelectedPet(pet); }} />
      )}
      {savedPets.length > 0 && <section className="space-y-3" aria-label="Saved collection">
        <div><h2 className="font-body font-bold text-lede text-ink-primary">Saved collection</h2>
          <p className="font-body text-caption text-ink-secondary">{savedPets.length} earlier {savedPets.length === 1 ? 'pet' : 'pets'}. Your saved pets keep their care and progress.</p></div>
        <OwnedPetGrid pets={savedPets} selectedPetId={selectedPet?.id} onSelect={setSelectedPet} label="Saved companions" />
      </section>}
      {carePet && (
        <BottomSheet title={`Care for ${carePet.name?.trim() || creatureLabel(carePet)}`} onClose={() => setSelectedPet(null)} disabled={working}>
          <ErrorAlert message={error || inventoryError} onRetry={inventoryError ? reloadInventory : undefined} />
          <p className="text-body text-ink-secondary mb-3">{carePet.evolved_to_mount ? 'Your companion is fully grown. Visit Grown pets to explore and collect expedition rewards.' : `${birdStage(carePet) ? `${birdFormName(carePet.species, carePet.potion, birdStage(carePet))} · ` : ''}${carePet.growth_points}/100 growth${carePet.species.food_preference ? ` · Prefers ${carePet.species.food_preference}` : ''}`}</p>
          {!carePet.is_active && (
            // <Button> for the 44px floor — this was a ~30px
            // text-xs button inside a 2-col phone tile.
            <Button
              size="sm"
              variant="secondary"
              onClick={(e) => { e.stopPropagation(); handleActivatePet(carePet.id); }}
              disabled={working}
              className="w-full !bg-moss/20 !text-moss !border-moss/50 hover:!bg-moss/30 disabled:cursor-not-allowed"
            >
              {working ? 'Setting…' : 'Set active'}
            </Button>
          )}
          {!carePet.evolved_to_mount && carePet.species.slug === 'companion' && (
            <div className="font-script text-tiny text-ink-whisper italic">
              Grows a little with each daily check-in.
            </div>
          )}
          {!carePet.evolved_to_mount && foods.length > 0 && (
            <div>
              <div className="font-script text-tiny text-ink-whisper mb-1">
                feed{carePet.species.food_preference ? ` · prefers ${carePet.species.food_preference}` : ''}
              </div>
              {/* One full-width row per food instead of 32px sprite
                  chips: feeding consumes the item on a single tap,
                  and the name lived only in `title`, which never
                  surfaces on touch — so a kid picking between
                  look-alike sprites was feeding blind. */}
              <div className="flex flex-col gap-2">
                {foods.map((f) => (
                  <button
                    key={f.item.id}
                    type="button"
                    onClick={(e) => { e.stopPropagation(); handleFeed(carePet, f.item.id); }}
                    disabled={working}
                    title={f.item.name}
                    className="w-full min-h-11 px-2 py-1 rounded bg-ink-page border border-ink-page-shadow hover:border-sheikah-teal/50 transition-colors flex items-center gap-2 text-left disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <CatalogIcon
                      assetId={f.item.catalog_icon}
                      spriteKey={f.item.sprite_key}
                      icon={f.item.icon}
                      size={24}
                      alt={f.item.name}
                    />
                    <span className="flex-1 min-w-0 font-body text-caption text-ink-primary break-words">
                      {f.item.name}
                    </span>
                    <span className="shrink-0 font-rune text-tiny text-ink-whisper tabular-nums">
                      ×{f.quantity}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {!carePet.evolved_to_mount && foods.length === 0 && !inventoryError && <p className="text-caption text-ink-secondary">No food in your inventory yet. Food you collect will appear here.</p>}
        </BottomSheet>
      )}
    </div>
  );
}
