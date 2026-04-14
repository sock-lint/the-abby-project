import { useState } from 'react';
import { motion } from 'framer-motion';
import { Sparkles, Crown, Star, X } from 'lucide-react';
import { getStable, getInventory, feedPet, activatePet, activateMount, hatchPet } from '../api';
import { useApi } from '../hooks/useApi';
import Loader from '../components/Loader';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import DeckleDivider from '../components/journal/DeckleDivider';
import { EggIcon, DragonIcon } from '../components/icons/JournalIcons';
import { normalizeList } from '../utils/api';
import { RARITY_RING_COLORS, RARITY_TEXT_COLORS } from '../constants/colors';
import { buttonPrimary, inputClass } from '../constants/styles';

export default function Stable() {
  const { data: stableData, loading: loadingStable, reload: reloadStable } = useApi(getStable);
  const { data: inventoryData, loading: loadingInventory, reload: reloadInventory } = useApi(getInventory);
  const [tab, setTab] = useState('pets');
  const [error, setError] = useState('');
  const [selectedPet, setSelectedPet] = useState(null);
  const [showHatch, setShowHatch] = useState(false);
  const [hatchEgg, setHatchEgg] = useState('');
  const [hatchPotion, setHatchPotion] = useState('');
  const [working, setWorking] = useState(false);

  if (loadingStable || loadingInventory) return <Loader />;

  const pets = stableData?.pets || [];
  const mounts = stableData?.mounts || [];
  const totalPossible = stableData?.total_possible || 0;

  const inventory = normalizeList(inventoryData);
  const eggs = inventory.filter((e) => e.item.item_type === 'egg');
  const potions = inventory.filter((e) => e.item.item_type === 'potion');
  const foods = inventory.filter((e) => e.item.item_type === 'food');

  const refresh = () => { reloadStable(); reloadInventory(); };

  const handleHatch = async () => {
    if (!hatchEgg || !hatchPotion) return;
    setWorking(true);
    setError('');
    try {
      await hatchPet(hatchEgg, hatchPotion);
      setShowHatch(false);
      setHatchEgg('');
      setHatchPotion('');
      refresh();
    } catch (e) { setError(e.message); }
    finally { setWorking(false); }
  };

  const handleFeed = async (petId, foodItemId) => {
    setWorking(true);
    setError('');
    try {
      await feedPet(petId, foodItemId);
      setSelectedPet(null);
      refresh();
    } catch (e) { setError(e.message); }
    finally { setWorking(false); }
  };

  const handleActivatePet = async (petId) => {
    setError('');
    try { await activatePet(petId); refresh(); }
    catch (e) { setError(e.message); }
  };

  const handleActivateMount = async (mountId) => {
    setError('');
    try { await activateMount(mountId); refresh(); }
    catch (e) { setError(e.message); }
  };

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            the party · companions, mounts & eggs
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Party
          </h1>
        </div>
        {eggs.length > 0 && potions.length > 0 && (
          <button
            type="button"
            onClick={() => setShowHatch(!showHatch)}
            className={`${buttonPrimary} px-3 py-2 flex items-center gap-1.5 text-sm`}
          >
            <Sparkles size={14} /> Hatch Pet
          </button>
        )}
      </header>

      <ErrorAlert message={error} />

      {/* Collection roster */}
      <div className="flex gap-2 flex-wrap">
        <RuneBadge tone="teal" size="md">
          pets {pets.length}/{totalPossible}
        </RuneBadge>
        <RuneBadge tone="gold" size="md">
          mounts {mounts.length}/{totalPossible}
        </RuneBadge>
      </div>

      {/* Hatch modal */}
      {showHatch && (
        <ParchmentCard flourish seal>
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="font-script text-xs text-ink-whisper uppercase tracking-widest">
                ritual casting
              </div>
              <h3 className="font-display text-lg text-ink-primary">Hatch a New Pet</h3>
            </div>
            <button
              type="button"
              onClick={() => setShowHatch(false)}
              aria-label="Close"
              className="p-1 rounded-full hover:bg-ink-page-shadow/50 transition-colors"
            >
              <X size={16} className="text-ink-secondary" />
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label
                htmlFor="hatch-egg"
                className="block font-script text-sm text-ink-secondary mb-1"
              >
                Egg
              </label>
              <select
                id="hatch-egg"
                className={inputClass}
                value={hatchEgg}
                onChange={(e) => setHatchEgg(e.target.value)}
              >
                <option value="">Select an egg…</option>
                {eggs.map((e) => (
                  <option key={e.item.id} value={e.item.id}>
                    {e.item.icon} {e.item.name} (×{e.quantity})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label
                htmlFor="hatch-potion"
                className="block font-script text-sm text-ink-secondary mb-1"
              >
                Potion
              </label>
              <select
                id="hatch-potion"
                className={inputClass}
                value={hatchPotion}
                onChange={(e) => setHatchPotion(e.target.value)}
              >
                <option value="">Select a potion…</option>
                {potions.map((e) => (
                  <option key={e.item.id} value={e.item.id}>
                    {e.item.icon} {e.item.name} (×{e.quantity})
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button
            type="button"
            onClick={handleHatch}
            disabled={!hatchEgg || !hatchPotion || working}
            className={`${buttonPrimary} w-full mt-3 py-2.5`}
          >
            {working ? 'Hatching…' : 'Perform the ritual'}
          </button>
        </ParchmentCard>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-ink-page-shadow">
        <TabPill active={tab === 'pets'} onClick={() => setTab('pets')}>
          Companions ({pets.length})
        </TabPill>
        <TabPill active={tab === 'mounts'} onClick={() => setTab('mounts')}>
          Mounts ({mounts.length})
        </TabPill>
      </div>

      {/* Pets */}
      {tab === 'pets' && (
        pets.length === 0 ? (
          <EmptyState icon={<EggIcon size={36} />}>
            No companions yet. Find eggs and potions in drops, then cast the ritual.
          </EmptyState>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {pets.map((pet) => (
              <motion.div key={pet.id} whileHover={{ y: -2 }}>
                <ParchmentCard
                  className={`cursor-pointer transition-all ${
                    pet.is_active
                      ? `ring-2 ring-offset-2 ring-offset-ink-page ring-moss`
                      : ''
                  }`}
                  onClick={() => setSelectedPet(selectedPet?.id === pet.id ? null : pet)}
                >
                  <div className="text-center">
                    <div className="text-5xl mb-1">{pet.species.icon}</div>
                    <div className="font-body text-sm font-medium leading-tight">
                      {pet.potion.name} {pet.species.name}
                    </div>
                    <div
                      className={`font-script text-[11px] uppercase tracking-wider ${
                        RARITY_TEXT_COLORS[pet.potion.rarity]
                      }`}
                    >
                      {pet.potion.rarity}
                    </div>
                    {!pet.evolved_to_mount && (
                      <div className="mt-2">
                        <div className="h-1.5 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-sheikah-teal-deep via-sheikah-teal to-gold-leaf"
                            style={{ width: `${pet.growth_points}%` }}
                          />
                        </div>
                        <div className="font-rune text-[10px] text-ink-whisper mt-0.5">
                          {pet.growth_points}/100
                        </div>
                      </div>
                    )}
                    {pet.evolved_to_mount && (
                      <div className="mt-1 font-script text-[11px] text-gold-leaf flex items-center justify-center gap-1">
                        <Crown size={10} /> evolved
                      </div>
                    )}
                    {pet.is_active && (
                      <div className="mt-1 font-script text-[11px] text-moss flex items-center justify-center gap-1">
                        <Star size={10} /> active
                      </div>
                    )}
                  </div>

                  {/* Actions drawer */}
                  {selectedPet?.id === pet.id && (
                    <div className="mt-3 pt-3 border-t border-ink-page-shadow/70 space-y-2">
                      {!pet.is_active && (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); handleActivatePet(pet.id); }}
                          className="w-full font-body text-xs py-1.5 rounded-lg bg-moss/20 text-moss border border-moss/50 hover:bg-moss/30 transition-colors"
                        >
                          Set active
                        </button>
                      )}
                      {!pet.evolved_to_mount && foods.length > 0 && (
                        <div>
                          <div className="font-script text-[11px] text-ink-whisper mb-1">
                            feed · prefers {pet.species.food_preference}
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {foods.map((f) => (
                              <button
                                key={f.item.id}
                                type="button"
                                onClick={(e) => { e.stopPropagation(); handleFeed(pet.id, f.item.id); }}
                                disabled={working}
                                title={f.item.name}
                                className="font-body text-xs px-2 py-1 rounded bg-ink-page border border-ink-page-shadow hover:border-sheikah-teal/50 transition-colors"
                              >
                                {f.item.icon} ×{f.quantity}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </ParchmentCard>
              </motion.div>
            ))}
          </div>
        )
      )}

      {/* Mounts */}
      {tab === 'mounts' && (
        mounts.length === 0 ? (
          <>
            <DeckleDivider glyph="dragon-crest" />
            <EmptyState icon={<DragonIcon size={36} />}>
              No mounts yet. Grow a companion to 100 to evolve it into a mount.
            </EmptyState>
          </>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {mounts.map((mount) => (
              <motion.div key={mount.id} whileHover={{ y: -2 }}>
                <ParchmentCard
                  className={`text-center cursor-pointer transition-all ${
                    mount.is_active
                      ? 'ring-2 ring-offset-2 ring-offset-ink-page ring-gold-leaf'
                      : ''
                  }`}
                >
                  <div className="text-6xl mb-1">{mount.species.icon}</div>
                  <div className="font-body text-sm font-medium leading-tight">
                    {mount.potion.name} {mount.species.name}
                  </div>
                  <div
                    className={`font-script text-[11px] uppercase tracking-wider ${
                      RARITY_TEXT_COLORS[mount.potion.rarity]
                    }`}
                  >
                    {mount.potion.rarity}
                  </div>
                  <div className="font-script text-[11px] text-gold-leaf mt-1">mount</div>
                  {mount.is_active ? (
                    <div className="mt-1 font-script text-[11px] text-gold-leaf flex items-center justify-center gap-1">
                      <Crown size={10} /> riding
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleActivateMount(mount.id)}
                      className="mt-2 w-full font-body text-xs py-1.5 rounded-lg bg-gold-leaf/20 text-ember-deep border border-gold-leaf/60 hover:bg-gold-leaf/30 transition-colors"
                    >
                      Saddle up
                    </button>
                  )}
                </ParchmentCard>
              </motion.div>
            ))}
          </div>
        )
      )}
    </div>
  );
}

function TabPill({ active, onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`relative px-4 py-2 font-display text-sm tracking-wide transition-colors rounded-t-lg border border-transparent -mb-px ${
        active
          ? 'bg-ink-page-aged text-ink-primary border-ink-page-shadow border-b-ink-page-aged'
          : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/40'
      }`}
    >
      {active && (
        <span
          className="absolute -top-1 left-1/2 -translate-x-1/2 w-5 h-0.5 rounded-b bg-sheikah-teal-deep"
          aria-hidden="true"
        />
      )}
      {children}
    </button>
  );
}
