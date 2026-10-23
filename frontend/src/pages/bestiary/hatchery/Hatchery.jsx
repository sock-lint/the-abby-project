import { useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { getIncubation, getInventory, getPetCodex, getStable, hatchIncubation, startIncubation } from '../../../api';
import { useApi } from '../../../hooks/useApi';
import Loader from '../../../components/Loader';
import EmptyState from '../../../components/EmptyState';
import ErrorAlert from '../../../components/ErrorAlert';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import { EggIcon } from '../../../components/icons/JournalIcons';
import { normalizeList } from '../../../utils/api';
import { isCatalogAvailable } from '../../../utils/catalogAvailability';
import Button from '../../../components/Button';
import { SelectField } from '../../../components/form';
import ChapterRubric from '../../../components/atlas/ChapterRubric';
import IncipitBand from '../../../components/atlas/IncipitBand';
import PetCeremonyModal from '../PetCeremonyModal';
import PedestalPreview from '../../../pedestal/PedestalPreview';
import PedestalImage from '../../../pedestal/PedestalImage';
import PetEvolutionGuide from '../../../components/companion/PetEvolutionGuide';
import PetSuppliesGuide from '../../../components/companion/PetSuppliesGuide';
import { companionFormName, eggSpecies } from '../../../companion/lifecycle';
import CatalogIcon from '../../../components/rpg/CatalogIcon';
import FamilyStagePreview from '../../../components/companion/FamilyStagePreview';
import { RARITY_TEXT_COLORS } from '../../../constants/colors';
import EggCollection from './EggCollection';
import usePetMutationGuard from '../party/usePetMutationGuard';
import IncubationCard from './IncubationCard';
import useIncubationRefresh from './useIncubationRefresh';
import { formatExpeditionRemaining } from '../party/party.constants';
import HatcheryDiscovery from './HatcheryDiscovery';

export default function Hatchery({ refreshRevision = 0, onChanged, showDiscovery = false } = {}) {
  const {
    data: stableData, loading: loadingStable, error: stableError, reload: reloadStable,
  } = useApi(getStable, [refreshRevision]);
  const {
    data: inventoryData, loading: loadingInventory, error: inventoryError,
    reload: reloadInventory,
  } = useApi(getInventory, [refreshRevision]);
  const {
    data: catalogData, loading: loadingCatalog, refreshing: refreshingCatalog,
    error: catalogError, reload: reloadCatalog,
  } = useApi(getPetCodex, [refreshRevision]);
  const {
    data: incubationData, loading: loadingIncubation, refreshing: refreshingIncubation,
    error: incubationError, reload: reloadIncubation, setData: setIncubationData,
  } = useApi(getIncubation, [refreshRevision]);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const [hatchEgg, setHatchEgg] = useState('');
  const [hatchPotion, setHatchPotion] = useState('');
  const [hatchSuccess, setHatchSuccess] = useState(null);
  const [hatchCeremony, setHatchCeremony] = useState(null);
  const [browseSelection, setBrowseSelection] = useState({});
  const recipeId = useId();
  const startRequest = useRef(null);
  const beginMutation = usePetMutationGuard();
  const incubation = incubationData?.incubation;
  useIncubationRefresh(incubation, reloadIncubation);

  // Incubation status, its retry, and hatch receipts are independent of the
  // supplies reads. Those reads have their own loading state below.
  if (loadingIncubation) return <Loader />;

  const mounts = stableData?.mounts || [];
  const inventory = normalizeList(inventoryData);
  const allEggs = inventory.filter((e) => e.item.item_type === 'egg' && e.quantity > 0);
  const eggs = allEggs.filter((e) => isCatalogAvailable(e.item));
  const potions = inventory.filter((e) => e.item.item_type === 'potion' && e.quantity > 0 && isCatalogAvailable(e.item));
  const selectedEggItem = eggs.find((entry) => String(entry.item.id) === hatchEgg)?.item;
  const selectedEggSpecies = eggSpecies(selectedEggItem);
  const selectedCatalogSpecies = (catalogData?.species || []).find((species) => species.slug === selectedEggSpecies?.slug && isCatalogAvailable(species));
  const compatibleVariants = (selectedCatalogSpecies?.available_potions || []).filter(isCatalogAvailable);
  const compatiblePotions = potions.filter((entry) => compatibleVariants.some((potion) => potion.slug === entry.item.metadata?.variant));
  const selectedPotionItem = compatiblePotions.find((entry) => String(entry.item.id) === hatchPotion)?.item;
  const selectedPotion = compatibleVariants.find((potion) => potion.slug === selectedPotionItem?.metadata?.variant);
  const alreadyOwned = selectedEggSpecies?.slug && selectedPotion?.slug
    && [...(stableData?.pets || []), ...mounts].some((pet) =>
      pet.species?.slug === selectedEggSpecies.slug && pet.potion?.slug === selectedPotion.slug);

  const refresh = () => { reloadStable(); reloadInventory(); reloadCatalog(); reloadIncubation(); };
  const changed = onChanged || refresh;
  const suppliesLoaded = !!inventoryData && !!stableData;
  const catalogReady = !!catalogData && !loadingCatalog && !refreshingCatalog && !catalogError;
  const selectEgg = (value) => {
    setHatchEgg(value);
    const item = eggs.find((entry) => String(entry.item.id) === value)?.item;
    const species = (catalogData?.species || []).find((entry) => entry.slug === item?.pet_species_slug);
    if (!(species?.available_potions || []).some((potion) => potion.slug === selectedPotion?.slug && isCatalogAvailable(potion))) setHatchPotion('');
    if (species) setBrowseSelection({ speciesSlug: species.slug, potionSlug: selectedPotion?.slug || 'base' });
  };
  const selectPotion = (value) => {
    setHatchPotion(value);
    const item = compatiblePotions.find((entry) => String(entry.item.id) === value)?.item;
    if (selectedCatalogSpecies && item) setBrowseSelection({
      speciesSlug: selectedCatalogSpecies.slug, potionSlug: item.metadata?.variant,
    });
  };

  // A failed satchel fetch used to render "No eggs or potions in your Satchel
  // yet — drops fall from clocked work…", which reads as "you own nothing"
  // rather than "we couldn't load it", with no way to retry.
  const fetchError = stableError || inventoryError || incubationError || catalogError;
  // Inventory supplies the ingredients and the stable prevents duplicate
  // hatches. Both reads are needed to show the available choices.
  if (incubationError && !incubationData) {
    return (
      <div className="space-y-3 max-w-xl mx-auto">
        <ErrorAlert message={fetchError} />
        <Button variant="secondary" size="sm" onClick={refresh}>
          Try again
        </Button>
      </div>
    );
  }

  const handleStart = async () => {
    if (!selectedEggItem || !selectedPotionItem || !catalogReady || alreadyOwned || incubation || fetchError || refreshingIncubation) return;
    const request = beginMutation();
    if (!request) return;
    setWorking(true);
    setError('');
    try {
      const pair = `${hatchEgg}:${hatchPotion}`;
      if (startRequest.current?.pair !== pair) startRequest.current = { pair, id: crypto.randomUUID() };
      const receipt = await startIncubation(hatchEgg, hatchPotion, startRequest.current.id);
      if (!request.isCurrent()) return;
      startRequest.current = null;
      const completed = receipt.incubation?.status === 'hatched';
      setIncubationData((previous) => ({ ...previous, ...receipt, incubation: completed ? null : receipt.incubation }));
      setHatchSuccess(completed ? {
        petId: receipt.incubation.pet_id,
        speciesName: companionFormName(receipt.incubation.species, receipt.incubation.potion_type, 'baby'),
        potionName: receipt.incubation.potion_type?.name,
        fresh: false,
      } : null);
      setHatchEgg('');
      setHatchPotion('');
      changed();
    } catch (e) {
      if (request.isCurrent()) { setError(e.message); void reloadIncubation(); }
    } finally { if (request.isCurrent()) setWorking(false); request.finish(); }
  };

  const handleHatch = async () => {
    if (!incubation?.is_ready || incubationError || refreshingIncubation) return;
    const request = beginMutation();
    if (!request) return;
    setWorking(true);
    setError('');
    try {
      const receipt = await hatchIncubation(incubation.id);
      if (!request.isCurrent()) return;
      const pet = receipt.pet;
      setIncubationData((previous) => ({ ...previous, ...receipt, incubation: null }));
      setHatchSuccess({
        petId: pet?.id,
        speciesName: companionFormName(pet?.species, pet?.potion, 'baby'),
        potionName: pet?.potion?.name,
        fresh: receipt.freshly_hatched === true,
      });
      if (receipt.freshly_hatched === true) setHatchCeremony(pet);
      changed();
    } catch (e) { if (request.isCurrent()) { setError(e.message); void reloadIncubation(); } }
    finally { if (request.isCurrent()) setWorking(false); request.finish(); }
  };

  return (
    <div className="space-y-6">
      {hatchCeremony && (
        <PetCeremonyModal
          mode="hatch"
          pet={hatchCeremony}
          onDismiss={() => setHatchCeremony(null)}
        />
      )}
      <IncipitBand
        letter="H"
        title="Hatchery"
        kicker="Your eggs and future companions"
      />

      <p className="font-script text-sm text-ink-whisper -mt-2 max-w-xl">
        Incubate one egg with one potion, then hatch a baby when it is ready. Care helps it reach its middle stage at 50 growth and its grown form at 100.
      </p>

      {/* Covers the partial case too — stable loaded, satchel didn't. */}
      <ErrorAlert message={error || fetchError} />
      {fetchError && <Button variant="secondary" size="sm" onClick={refresh}>Try again</Button>}

      {incubation && <IncubationCard egg={incubation.egg} potion={incubation.potion}
        remainingSeconds={incubation.remaining_seconds} isReady={incubation.is_ready}
        snapshotKey={incubation} working={working} refreshing={refreshingIncubation} blocked={!!incubationError}
        onHatch={handleHatch} onRefresh={reloadIncubation} />}

      {/* The skip link passes over the staff-only discovery panel. */}
      {showDiscovery && eggs.length > 0 && <a href={'#' + recipeId}
        className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep">
        Choose ingredients for incubation
      </a>}
      {showDiscovery && <HatcheryDiscovery catalog={catalogData} stable={stableData} incubation={incubation}
        loading={loadingCatalog} refreshing={refreshingCatalog} catalogError={catalogError}
        stableError={stableError} incubationError={incubationError}
        selection={browseSelection} onSelect={setBrowseSelection} />}

      {suppliesLoaded ? <>
      <div id={recipeId} className="scroll-mt-24">
      <EggCollection eggs={allEggs.map((entry) => ({ ...entry, available: isCatalogAvailable(entry.item) }))}
        potionCount={potions.reduce((total, entry) => total + entry.quantity, 0)}
        selectedId={hatchEgg} onSelect={selectEgg} working={working || !!incubation} />
      </div>

      <ParchmentCard flourish>
        <ChapterRubric index={0} name="Incubate a new pet" icon="✨" />
        <p className="font-script text-sm text-ink-whisper mb-3">
          Choose an available egg and a compatible potion. Incubation takes {formatExpeditionRemaining(incubationData?.duration_seconds) || 'some time'} and continues while you are away.
        </p>

        {eggs.length === 0 ? (
          <EmptyState icon={<EggIcon size={28} />}>
            {potions.length === 0
              ? 'No eggs or potions for new hatching yet. You can earn them from project work, chores, homework, and challenges.'
              : 'No eggs for new hatching yet. You can earn them from challenges and project completions.'}
          </EmptyState>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
            <figure className="min-w-0">
              {/* Staff preview the selected family in Explore companions; everyone
                  else keeps the owned egg's artwork and growth stages here. */}
              {selectedEggItem?.slug ? showDiscovery ? <div className="flex h-48 items-center justify-center">
                <CatalogIcon assetId={selectedEggItem.catalog_icon} icon={selectedEggItem.icon || '🥚'} alt={selectedEggItem.name} size={160} />
              </div> : <FamilyStagePreview key={selectedEggItem.id} item={selectedEggItem} potion={selectedPotion} />
                : <PedestalPreview />}
              <figcaption className="flex items-center justify-center gap-2 text-caption text-ink-secondary">
                <span className="w-12 shrink-0"><PedestalImage assetId="card-front-egg-star" /></span>
                Your selected egg
              </figcaption>
            </figure>
            <div className="min-w-0">
            <div className="grid grid-cols-1 gap-3">
              <SelectField
                id="hatch-egg"
                label="Egg"
                value={hatchEgg}
                disabled={working || !!incubation}
                onChange={(e) => selectEgg(e.target.value)}
              >
                <option value="">Select an egg…</option>
                {eggs.map((e) => (
                  <option key={e.item.id} value={e.item.id}>
                    {e.item.icon} {e.item.name}{e.item.rarity ? ` · ${e.item.rarity}` : ''} (×{e.quantity})
                  </option>
                ))}
              </SelectField>
              <SelectField
                id="hatch-potion"
                label="Potion"
                value={selectedPotionItem ? hatchPotion : ''}
                disabled={working || !!incubation || !selectedEggItem || !catalogReady || compatiblePotions.length === 0}
                onChange={(e) => selectPotion(e.target.value)}
              >
                <option value="">Select a potion…</option>
                {compatiblePotions.map((e) => (
                  <option key={e.item.id} value={e.item.id}>
                    {e.item.icon} {e.item.name} (×{e.quantity})
                  </option>
                ))}
              </SelectField>
            </div>
            {(loadingCatalog || refreshingCatalog) && <p role="status" className="mt-3 text-body text-ink-secondary">Checking compatible potions…</p>}
            {selectedEggItem && catalogReady && potions.length > 0 && compatiblePotions.length === 0 && <p className="mt-3 text-body text-ink-secondary">None of your potions can hatch this egg. Choose another egg or earn a compatible potion from challenges.</p>}
            {potions.length === 0 && <p className="mt-3 text-body text-ink-secondary">No potions for new hatching yet. You can still explore your eggs and their growth stages.</p>}
            {selectedPotion && <p role="status" className="mt-3 text-body text-ink-primary">Selected appearance: {selectedPotion.name} {companionFormName(selectedEggSpecies, selectedPotion, 'baby')}. The same appearance continues through every growth stage.</p>}
            {alreadyOwned && <div className="mt-3 space-y-1 text-body text-ink-secondary">
              <p>You already have this companion. Extra eggs stay in your inventory.</p>
              <Link className="inline-flex min-h-11 items-center font-semibold text-sheikah-teal-deep" to="/bestiary?tab=companions">Care for companions</Link>
            </div>}
            <Button
              onClick={handleStart}
              disabled={!selectedEggItem || !selectedPotionItem || !catalogReady || alreadyOwned || working || !!incubation || !!fetchError || refreshingIncubation}
              className="w-full mt-3"
            >
              {working && !incubation ? 'Starting…' : 'Start incubation'}
            </Button>
            <p className="mt-2 text-caption text-ink-secondary">Starting incubation uses 1 egg and 1 potion. Each species and potion pair can join your collection once.</p>
            {incubation && <p className="mt-2 text-caption text-ink-secondary">Finish hatching your current egg before starting another.</p>}
            </div>
          </div>
        )}

        {(eggs.length === 0 || potions.length === 0) && <div className="mt-3"><PetSuppliesGuide /></div>}

        {selectedEggSpecies && <section className="mt-4 space-y-2" aria-label="Selected egg family">
          <h4 className="text-body font-semibold text-ink-primary">{selectedEggSpecies.name} family</h4>
          {selectedEggItem.rarity && <p className={`text-caption ${RARITY_TEXT_COLORS[selectedEggItem.rarity] || ''}`}>
            {selectedEggItem.rarity} companion · rarity stays the same as it grows
          </p>}
          <p className="text-caption text-ink-secondary">Hatches into a baby {selectedEggSpecies.name}.</p>
          <PetEvolutionGuide species={selectedEggSpecies} potion={selectedPotion} currentStage="egg" />
        </section>}

      </ParchmentCard>
      </> : (loadingStable || loadingInventory) && <Loader />}

      {hatchSuccess && (
          <div className="space-y-2 font-body text-body">
            <p role="status" className="text-moss">{hatchSuccess.fresh
              ? `✨ You hatched a ${hatchSuccess.potionName} ${hatchSuccess.speciesName}!`
              : `Your ${hatchSuccess.potionName} ${hatchSuccess.speciesName} is ready for care.`}</p>
            <Link className="inline-flex min-h-11 items-center font-semibold text-sheikah-teal-deep"
              to={`/bestiary?tab=companions${hatchSuccess.petId != null ? `&pet=${encodeURIComponent(hatchSuccess.petId)}` : ''}`}>
              Care for your new pet
            </Link>
          </div>
        )}
    </div>
  );
}
