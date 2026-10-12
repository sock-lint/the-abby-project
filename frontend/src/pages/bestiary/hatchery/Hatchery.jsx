import { useState } from 'react';
import { breedMounts, getInventory, getStable, hatchPet } from '../../../api';
import { useApi } from '../../../hooks/useApi';
import Loader from '../../../components/Loader';
import EmptyState from '../../../components/EmptyState';
import ErrorAlert from '../../../components/ErrorAlert';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import RuneBadge from '../../../components/journal/RuneBadge';
import { EggIcon, DragonIcon } from '../../../components/icons/JournalIcons';
import { normalizeList } from '../../../utils/api';
import Button from '../../../components/Button';
import { SelectField } from '../../../components/form';
import ChapterRubric from '../../../components/atlas/ChapterRubric';
import IncipitBand from '../../../components/atlas/IncipitBand';
import { BREEDING_COOLDOWN_DAYS, daysUntilReady } from '../party/party.constants';
import PetCeremonyModal from '../PetCeremonyModal';

const CHROMATIC_UPGRADE_RATE = '1 in 50';

/**
 * Hatchery — dedicated tab for the two ritual flows that used to live as
 * modals on the Party tab. Stacks Hatch a New Pet + Breed Two Mounts as
 * inline panels, surfaces breeding cooldowns inline (replaces the
 * "rest 7 days" copy with concrete per-mount countdowns), and prints
 * the chromatic-upgrade odds so the wildcard outcome isn't a surprise.
 */
export default function Hatchery() {
  const {
    data: stableData, loading: loadingStable, error: stableError, reload: reloadStable,
  } = useApi(getStable);
  const {
    data: inventoryData, loading: loadingInventory, error: inventoryError,
    reload: reloadInventory,
  } = useApi(getInventory);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const [hatchEgg, setHatchEgg] = useState('');
  const [hatchPotion, setHatchPotion] = useState('');
  const [hatchSuccess, setHatchSuccess] = useState(null);
  const [hatchCeremony, setHatchCeremony] = useState(null);
  const [breedA, setBreedA] = useState('');
  const [breedB, setBreedB] = useState('');
  const [breedCeremony, setBreedCeremony] = useState(null);

  if (loadingStable || loadingInventory) return <Loader />;

  const mounts = stableData?.mounts || [];
  const inventory = normalizeList(inventoryData);
  const eggs = inventory.filter((e) => e.item.item_type === 'egg');
  const potions = inventory.filter((e) => e.item.item_type === 'potion');

  const refresh = () => { reloadStable(); reloadInventory(); };

  // A failed satchel fetch used to render "No eggs or potions in your Satchel
  // yet — drops fall from clocked work…", which reads as "you own nothing"
  // rather than "we couldn't load it", with no way to retry.
  const fetchError = stableError || inventoryError;
  // Both panels need both feeds — the hatch ritual reads the satchel, the
  // breed ritual reads the stable — so either one missing means the page
  // can't tell the truth about what you own.
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

  const mountReadiness = mounts.map((m) => ({
    mount: m,
    cooldownDaysLeft: daysUntilReady(m.last_bred_at),
  }));
  const readyMounts = mountReadiness.filter((m) => m.cooldownDaysLeft === null);

  const handleHatch = async () => {
    if (!hatchEgg || !hatchPotion) return;
    setWorking(true);
    setError('');
    try {
      const pet = await hatchPet(hatchEgg, hatchPotion);
      setHatchSuccess({
        speciesName: pet?.species?.name,
        potionName: pet?.potion?.name,
      });
      setHatchCeremony(pet);
      setHatchEgg('');
      setHatchPotion('');
      refresh();
    } catch (e) { setError(e.message); }
    finally { setWorking(false); }
  };

  const handleBreed = async () => {
    if (!breedA || !breedB || breedA === breedB) return;
    setWorking(true);
    setError('');
    // Capture the parent mount objects BEFORE refresh — the dropdowns
    // clear and reloadStable swaps the array, so we'd lose the species/
    // potion data the celebration needs.
    const parentA = mounts.find((m) => String(m.id) === String(breedA));
    const parentB = mounts.find((m) => String(m.id) === String(breedB));
    try {
      const result = await breedMounts(breedA, breedB);
      if (parentA && parentB) {
        setBreedCeremony({ parents: [parentA, parentB], result });
      }
      setBreedA('');
      setBreedB('');
      refresh();
    } catch (e) { setError(e.message); }
    finally { setWorking(false); }
  };

  const cantHatch = eggs.length === 0 || potions.length === 0;

  return (
    <div className="space-y-6">
      {hatchCeremony && (
        <PetCeremonyModal
          mode="hatch"
          pet={hatchCeremony}
          onDismiss={() => setHatchCeremony(null)}
        />
      )}
      {breedCeremony && (
        <PetCeremonyModal
          mode="breed"
          parents={breedCeremony.parents}
          result={breedCeremony.result}
          onDismiss={() => setBreedCeremony(null)}
        />
      )}
      <IncipitBand
        letter="H"
        title="Hatching"
        kicker="Hatch companions and breed mounts"
        meta={
          mounts.length >= 2 ? (
            <>
              <span className="tabular-nums">{readyMounts.length}</span>
              <span>mounts ready to breed</span>
            </>
          ) : null
        }
        progressPct={mounts.length >= 2 ? (readyMounts.length / mounts.length) * 100 : 0}
      />

      <p className="font-script text-sm text-ink-whisper -mt-2 max-w-xl">
        Combine an egg and a potion to hatch a companion. Breed two mounts to get a hybrid egg and potion.
      </p>

      {/* Covers the partial case too — stable loaded, satchel didn't. */}
      <ErrorAlert message={error || fetchError} />

      <ParchmentCard flourish>
        <ChapterRubric index={0} name="Hatch a new pet" icon="✨" />
        <p className="font-script text-sm text-ink-whisper mb-3">
          Choose an egg and a potion. The potion determines your new companion's color.
        </p>

        {cantHatch ? (
          <EmptyState icon={<EggIcon size={28} />}>
            {eggs.length === 0 && potions.length === 0
              ? 'No eggs or potions in your inventory yet. You can earn them from project work, chores, homework, and challenges.'
              : eggs.length === 0
                ? 'No eggs yet. You can earn them from challenges, project completions, and breeding mounts.'
                : 'No potions yet. You can earn them from item drops and breeding mounts.'}
          </EmptyState>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <SelectField
                id="hatch-egg"
                label="Egg"
                value={hatchEgg}
                onChange={(e) => setHatchEgg(e.target.value)}
              >
                <option value="">Select an egg…</option>
                {eggs.map((e) => (
                  <option key={e.item.id} value={e.item.id}>
                    {e.item.icon} {e.item.name} (×{e.quantity})
                  </option>
                ))}
              </SelectField>
              <SelectField
                id="hatch-potion"
                label="Potion"
                value={hatchPotion}
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
            <Button
              onClick={handleHatch}
              disabled={!hatchEgg || !hatchPotion || working}
              className="w-full mt-3"
            >
              {working ? 'Hatching…' : 'Hatch pet'}
            </Button>
          </>
        )}

        {hatchSuccess && (
          <div role="status" className="mt-3 font-body text-body text-moss">
            ✨ You hatched a {hatchSuccess.potionName} {hatchSuccess.speciesName}!
          </div>
        )}
      </ParchmentCard>

      <ParchmentCard flourish>
        <ChapterRubric index={1} name="Breed two mounts" icon="👑" />
        <p className="font-script text-sm text-ink-whisper">
          Get a hybrid egg and potion. Each mount needs {BREEDING_COOLDOWN_DAYS} days between pairings.
        </p>
        <div className="font-script text-tiny text-gold-leaf mt-1">
          ✨ Each pairing has a {CHROMATIC_UPGRADE_RATE} chance of a Cosmic potion when the chosen species supports it.
        </div>

        {mounts.length < 2 ? (
          <div className="mt-4">
            <EmptyState icon={<DragonIcon size={28} />}>
              You need at least two mounts to breed. Grow companions to 100 to evolve them into mounts.
            </EmptyState>
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            <div className="flex flex-wrap gap-2">
              <RuneBadge tone="teal" size="sm">{readyMounts.length} ready to breed</RuneBadge>
              {mounts.length - readyMounts.length > 0 && (
                <RuneBadge tone="ink" size="sm">
                  {mounts.length - readyMounts.length} resting
                </RuneBadge>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <SelectField
                id="breed-a"
                label="First mount"
                value={breedA}
                onChange={(e) => setBreedA(e.target.value)}
              >
                <option value="">Select a mount…</option>
                {mountReadiness.map(({ mount, cooldownDaysLeft }) => (
                  <option
                    key={mount.id}
                    value={mount.id}
                    disabled={cooldownDaysLeft !== null}
                  >
                    {mount.species.icon} {mount.potion.name} {mount.species.name}
                    {cooldownDaysLeft !== null
                      ? ` · resting ${cooldownDaysLeft}d`
                      : ' · ready'}
                  </option>
                ))}
              </SelectField>
              <SelectField
                id="breed-b"
                label="Second mount"
                value={breedB}
                onChange={(e) => setBreedB(e.target.value)}
              >
                <option value="">Select a mount…</option>
                {mountReadiness
                  .filter(({ mount }) => String(mount.id) !== String(breedA))
                  .map(({ mount, cooldownDaysLeft }) => (
                    <option
                      key={mount.id}
                      value={mount.id}
                      disabled={cooldownDaysLeft !== null}
                    >
                      {mount.species.icon} {mount.potion.name} {mount.species.name}
                      {cooldownDaysLeft !== null
                        ? ` · resting ${cooldownDaysLeft}d`
                        : ' · ready'}
                    </option>
                  ))}
              </SelectField>
            </div>
            <Button
              onClick={handleBreed}
              disabled={!breedA || !breedB || breedA === breedB || working}
              className="w-full"
            >
              {working ? 'Breeding…' : 'Breed mounts'}
            </Button>
          </div>
        )}
      </ParchmentCard>
    </div>
  );
}
