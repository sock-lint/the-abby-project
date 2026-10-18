import { useState } from 'react';
import { Link } from 'react-router-dom';
import { getInventory, getStable, hatchPet } from '../../../api';
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
import { companionFormName, eggSpecies } from '../../../companion/lifecycle';
import FamilyStagePreview from '../../../components/companion/FamilyStagePreview';
import { RARITY_TEXT_COLORS } from '../../../constants/colors';
import EggCollection from './EggCollection';
import usePetMutationGuard from '../party/usePetMutationGuard';

export default function Hatchery({ refreshRevision = 0, onChanged } = {}) {
  const {
    data: stableData, loading: loadingStable, error: stableError, reload: reloadStable,
  } = useApi(getStable, [refreshRevision]);
  const {
    data: inventoryData, loading: loadingInventory, error: inventoryError,
    reload: reloadInventory,
  } = useApi(getInventory, [refreshRevision]);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const [hatchEgg, setHatchEgg] = useState('');
  const [hatchPotion, setHatchPotion] = useState('');
  const [hatchSuccess, setHatchSuccess] = useState(null);
  const [hatchCeremony, setHatchCeremony] = useState(null);
  const beginMutation = usePetMutationGuard();

  if (loadingStable || loadingInventory) return <Loader />;

  const mounts = stableData?.mounts || [];
  const inventory = normalizeList(inventoryData);
  const allEggs = inventory.filter((e) => e.item.item_type === 'egg' && e.quantity > 0);
  const eggs = allEggs.filter((e) => isCatalogAvailable(e.item));
  const potions = inventory.filter((e) => e.item.item_type === 'potion' && e.quantity > 0 && isCatalogAvailable(e.item));
  const selectedEggItem = eggs.find((entry) => String(entry.item.id) === hatchEgg)?.item;
  const selectedEggSpecies = eggSpecies(selectedEggItem);
  const selectedPotionItem = potions.find((entry) => String(entry.item.id) === hatchPotion)?.item;
  const selectedPotion = { slug: selectedPotionItem?.metadata?.variant };
  const alreadyOwned = selectedEggSpecies?.slug && selectedPotion.slug
    && [...(stableData?.pets || []), ...mounts].some((pet) =>
      pet.species?.slug === selectedEggSpecies.slug && pet.potion?.slug === selectedPotion.slug);

  const refresh = () => { reloadStable(); reloadInventory(); };
  const changed = onChanged || refresh;

  // A failed satchel fetch used to render "No eggs or potions in your Satchel
  // yet — drops fall from clocked work…", which reads as "you own nothing"
  // rather than "we couldn't load it", with no way to retry.
  const fetchError = stableError || inventoryError;
  // Inventory supplies the ingredients and the stable prevents duplicate
  // hatches. Both reads are needed to show the available choices.
  if (fetchError && (!inventoryData || !stableData)) {
    return (
      <div className="space-y-3 max-w-xl mx-auto">
        <ErrorAlert message={fetchError} />
        <Button variant="secondary" size="sm" onClick={refresh}>
          Try again
        </Button>
      </div>
    );
  }

  const handleHatch = async () => {
    if (!selectedEggItem || !selectedPotionItem || alreadyOwned) return;
    const request = beginMutation();
    if (!request) return;
    setWorking(true);
    setError('');
    try {
      const pet = await hatchPet(hatchEgg, hatchPotion);
      if (!request.isCurrent()) return;
      setHatchSuccess({
        speciesName: companionFormName(pet?.species, pet?.potion, 'baby'),
        potionName: pet?.potion?.name,
      });
      setHatchCeremony(pet);
      setHatchEgg('');
      setHatchPotion('');
      changed();
    } catch (e) { if (request.isCurrent()) setError(e.message); }
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
        Combine one egg and one potion to hatch a baby. Care helps it reach its middle stage at 50 growth and its grown form at 100.
      </p>

      {/* Covers the partial case too — stable loaded, satchel didn't. */}
      <ErrorAlert message={error || fetchError} />

      <EggCollection eggs={allEggs.map((entry) => ({ ...entry, available: isCatalogAvailable(entry.item) }))}
        potionCount={potions.reduce((total, entry) => total + entry.quantity, 0)}
        selectedId={hatchEgg} onSelect={setHatchEgg} working={working} />

      <ParchmentCard flourish>
        <ChapterRubric index={0} name="Hatch a new pet" icon="✨" />
        <p className="font-script text-sm text-ink-whisper mb-3">
          Choose an available egg and a compatible potion to hatch your companion.
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
              {selectedEggItem?.slug ? <FamilyStagePreview key={selectedEggItem.id} item={selectedEggItem} /> : <PedestalPreview />}
              <figcaption className="flex items-center justify-center gap-2 text-caption text-ink-secondary">
                <span className="w-12 shrink-0"><PedestalImage assetId="card-front-egg-star" /></span>
                Family artwork preview
              </figcaption>
            </figure>
            <div className="min-w-0">
            <div className="grid grid-cols-1 gap-3">
              <SelectField
                id="hatch-egg"
                label="Egg"
                value={hatchEgg}
                disabled={working}
                onChange={(e) => setHatchEgg(e.target.value)}
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
                value={hatchPotion}
                disabled={working || potions.length === 0}
                onChange={(e) => setHatchPotion(e.target.value)}
              >
                <option value="">Select a potion…</option>
                {potions.map((e) => (
                  <option key={e.item.id} value={e.item.id}>
                    {e.item.icon} {e.item.name} (×{e.quantity})
                  </option>
                ))}
              </SelectField>
            </div>
            {potions.length === 0 && <p className="mt-3 text-body text-ink-secondary">No potions for new hatching yet. You can still explore your eggs and their growth stages.</p>}
            {alreadyOwned && <div className="mt-3 space-y-1 text-body text-ink-secondary">
              <p>You already have this companion. Extra eggs stay in your inventory.</p>
              <Link className="inline-flex min-h-11 items-center font-semibold text-sheikah-teal-deep" to="/bestiary?tab=companions">Care for companions</Link>
            </div>}
            <Button
              onClick={handleHatch}
              disabled={!selectedEggItem || !selectedPotionItem || alreadyOwned || working}
              className="w-full mt-3"
            >
              {working ? 'Hatching…' : 'Hatch pet'}
            </Button>
            <p className="mt-2 text-caption text-ink-secondary">Hatching uses 1 egg and 1 potion. Each species and potion pair can join your collection once.</p>
            </div>
          </div>
        )}

        {selectedEggSpecies && <section className="mt-4 space-y-2" aria-label="Selected egg family">
          <h4 className="text-body font-semibold text-ink-primary">{selectedEggSpecies.name} family</h4>
          {selectedEggItem.rarity && <p className={`text-caption ${RARITY_TEXT_COLORS[selectedEggItem.rarity] || ''}`}>
            {selectedEggItem.rarity} companion · rarity stays the same as it grows
          </p>}
          <p className="text-caption text-ink-secondary">Hatches into a baby {selectedEggSpecies.name}.</p>
          <PetEvolutionGuide species={selectedEggSpecies} potion={selectedPotion} currentStage="egg" />
        </section>}

        {hatchSuccess && (
          <div role="status" className="mt-3 font-body text-body text-moss">
            ✨ You hatched a {hatchSuccess.potionName} {hatchSuccess.speciesName}!
          </div>
        )}
      </ParchmentCard>
    </div>
  );
}
