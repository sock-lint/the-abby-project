import { useState } from 'react';
import { Sparkles, Crown } from 'lucide-react';
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
import { BREEDING_COOLDOWN_DAYS, daysUntilReady } from '../party/party.constants';

const CHROMATIC_UPGRADE_RATE = '1 in 50';

/**
 * Hatchery — dedicated tab for the two ritual flows that used to live as
 * modals on the Party tab. Stacks Hatch a New Pet + Breed Two Mounts as
 * inline panels, surfaces breeding cooldowns inline (replaces the
 * "rest 7 days" copy with concrete per-mount countdowns), and prints
 * the chromatic-upgrade odds so the wildcard outcome isn't a surprise.
 */
export default function Hatchery() {
  const { data: stableData, loading: loadingStable, reload: reloadStable } = useApi(getStable);
  const { data: inventoryData, loading: loadingInventory, reload: reloadInventory } = useApi(getInventory);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const [hatchEgg, setHatchEgg] = useState('');
  const [hatchPotion, setHatchPotion] = useState('');
  const [hatchSuccess, setHatchSuccess] = useState(null);
  const [breedA, setBreedA] = useState('');
  const [breedB, setBreedB] = useState('');
  const [breedResult, setBreedResult] = useState(null);

  if (loadingStable || loadingInventory) return <Loader />;

  const mounts = stableData?.mounts || [];
  const inventory = normalizeList(inventoryData);
  const eggs = inventory.filter((e) => e.item.item_type === 'egg');
  const potions = inventory.filter((e) => e.item.item_type === 'potion');

  const refresh = () => { reloadStable(); reloadInventory(); };

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
    try {
      const result = await breedMounts(breedA, breedB);
      setBreedResult(result);
      setBreedA('');
      setBreedB('');
      refresh();
    } catch (e) { setError(e.message); }
    finally { setWorking(false); }
  };

  const cantHatch = eggs.length === 0 || potions.length === 0;

  return (
    <div className="space-y-6">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base">
          the hatchery · ritual casting & stable husbandry
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Hatchery
        </h1>
        <div className="font-script text-sm text-ink-whisper mt-1 max-w-xl">
          pair an egg + potion to summon a companion · pair two mounts to inherit a hybrid egg & potion
        </div>
      </header>

      <ErrorAlert message={error} />

      <ParchmentCard flourish>
        <div className="flex items-center gap-2 mb-1">
          <Sparkles size={16} className="text-sheikah-teal-deep" />
          <h2 className="font-display text-xl text-ink-primary">Hatch a New Pet</h2>
        </div>
        <p className="font-script text-sm text-ink-whisper mb-3">
          pair an egg with a potion to summon a new companion · the potion tints its colour
        </p>

        {cantHatch ? (
          <EmptyState icon={<EggIcon size={28} />}>
            {eggs.length === 0 && potions.length === 0
              ? 'No eggs or potions in your Satchel yet — drops fall from clocked work, duties, study, and quests.'
              : eggs.length === 0
                ? 'No eggs yet — drops from quests + project completions are the most reliable source.'
                : 'No potions yet — drops + breeding rewards are the main sources.'}
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
              {working ? 'Hatching…' : 'Perform the ritual'}
            </Button>
          </>
        )}

        {hatchSuccess && (
          <div role="status" className="mt-3 font-body text-body text-moss">
            ✨ A {hatchSuccess.potionName} {hatchSuccess.speciesName} has joined your party.
          </div>
        )}
      </ParchmentCard>

      <ParchmentCard flourish>
        <div className="flex items-center gap-2 mb-1">
          <Crown size={16} className="text-gold-leaf" />
          <h2 className="font-display text-xl text-ink-primary">Breed Two Mounts</h2>
        </div>
        <p className="font-script text-sm text-ink-whisper">
          yields a hybrid egg + potion pair · each mount rests {BREEDING_COOLDOWN_DAYS} days between pairings
        </p>
        <div className="font-script text-tiny text-gold-leaf mt-1">
          ✨ {CHROMATIC_UPGRADE_RATE} breeds yield a chromatic Cosmic potion, regardless of parents
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

            {breedResult ? (
              <div className="space-y-2 text-body">
                {breedResult.chromatic && (
                  <div className="font-script text-gold-leaf">
                    ✨ Chromatic upgrade! A Cosmic potion fell from the stars.
                  </div>
                )}
                <div>
                  You received <strong>{breedResult.egg_item_name}</strong> and{' '}
                  <strong>{breedResult.potion_item_name}</strong>.
                </div>
                <div className="text-tiny text-ink-whisper">
                  Both parent mounts are resting for {breedResult.cooldown_days} days.
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => setBreedResult(null)}
                >
                  Breed more
                </Button>
              </div>
            ) : (
              <>
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
                  {working ? 'Breeding…' : 'Breed the pair'}
                </Button>
              </>
            )}
          </div>
        )}
      </ParchmentCard>
    </div>
  );
}
