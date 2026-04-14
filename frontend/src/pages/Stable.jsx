import { useState } from 'react';
import { motion } from 'framer-motion';
import { Heart, Sparkles, Star, Crown } from 'lucide-react';
import { getStable, getInventory, feedPet, activatePet, activateMount, hatchPet } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import ProgressBar from '../components/ProgressBar';
import TabButton from '../components/TabButton';
import { normalizeList } from '../utils/api';

const RARITY_COLORS = {
  common: 'text-gray-400',
  uncommon: 'text-green-400',
  rare: 'text-blue-400',
  epic: 'text-purple-400',
  legendary: 'text-amber-400',
};

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
  const eggs = inventory.filter(e => e.item.item_type === 'egg');
  const potions = inventory.filter(e => e.item.item_type === 'potion');
  const foods = inventory.filter(e => e.item.item_type === 'food');

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
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold flex items-center gap-2">
          <Heart size={22} /> Stable
        </h1>
        {eggs.length > 0 && potions.length > 0 && (
          <button
            onClick={() => setShowHatch(!showHatch)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-primary text-white text-sm font-medium"
          >
            <Sparkles size={14} /> Hatch Pet
          </button>
        )}
      </div>

      <ErrorAlert message={error} />

      {/* Collection Stats */}
      <div className="flex gap-4 text-sm text-forge-text-dim">
        <span>Pets: {pets.length}/{totalPossible}</span>
        <span>Mounts: {mounts.length}/{totalPossible}</span>
      </div>

      {/* Hatch Modal */}
      {showHatch && (
        <Card className="space-y-3">
          <h3 className="font-heading font-bold text-sm">Hatch a New Pet</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-forge-text-dim mb-1">Egg</label>
              <select className="w-full bg-forge-surface-alt rounded px-2 py-1.5 text-sm" value={hatchEgg} onChange={e => setHatchEgg(e.target.value)}>
                <option value="">Select egg...</option>
                {eggs.map(e => (
                  <option key={e.item.id} value={e.item.id}>{e.item.icon} {e.item.name} (x{e.quantity})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-forge-text-dim mb-1">Potion</label>
              <select className="w-full bg-forge-surface-alt rounded px-2 py-1.5 text-sm" value={hatchPotion} onChange={e => setHatchPotion(e.target.value)}>
                <option value="">Select potion...</option>
                {potions.map(e => (
                  <option key={e.item.id} value={e.item.id}>{e.item.icon} {e.item.name} (x{e.quantity})</option>
                ))}
              </select>
            </div>
          </div>
          <button onClick={handleHatch} disabled={!hatchEgg || !hatchPotion || working} className="w-full py-2 rounded-lg bg-amber-primary text-white text-sm font-medium disabled:opacity-50">
            {working ? 'Hatching...' : 'Hatch!'}
          </button>
        </Card>
      )}

      {/* Tabs */}
      <div className="flex gap-2">
        <TabButton active={tab === 'pets'} onClick={() => setTab('pets')}>Pets ({pets.length})</TabButton>
        <TabButton active={tab === 'mounts'} onClick={() => setTab('mounts')}>Mounts ({mounts.length})</TabButton>
      </div>

      {/* Pets Tab */}
      {tab === 'pets' && (
        pets.length === 0 ? (
          <EmptyState>No pets yet. Collect eggs and potions from drops, then hatch!</EmptyState>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {pets.map(pet => (
              <motion.div key={pet.id} whileHover={{ y: -2 }}>
                <Card
                  className={`cursor-pointer ${pet.is_active ? 'ring-2 ring-green-400' : ''}`}
                  onClick={() => setSelectedPet(selectedPet?.id === pet.id ? null : pet)}
                >
                  <div className="text-center">
                    <div className="text-4xl mb-1">{pet.species.icon}</div>
                    <div className="text-xs font-medium">{pet.potion.name} {pet.species.name}</div>
                    <div className={`text-[10px] ${RARITY_COLORS[pet.potion.rarity]}`}>{pet.potion.rarity}</div>
                    {!pet.evolved_to_mount && (
                      <div className="mt-2">
                        <ProgressBar value={pet.growth_points} max={100} />
                        <div className="text-[10px] text-forge-text-dim mt-0.5">{pet.growth_points}/100</div>
                      </div>
                    )}
                    {pet.evolved_to_mount && (
                      <div className="mt-1 text-[10px] text-amber-highlight flex items-center justify-center gap-1">
                        <Crown size={10} /> Evolved
                      </div>
                    )}
                    {pet.is_active && (
                      <div className="mt-1 text-[10px] text-green-400 flex items-center justify-center gap-1">
                        <Star size={10} /> Active
                      </div>
                    )}
                  </div>

                  {/* Actions panel */}
                  {selectedPet?.id === pet.id && (
                    <div className="mt-3 pt-3 border-t border-forge-surface-alt space-y-2">
                      {!pet.is_active && (
                        <button onClick={(e) => { e.stopPropagation(); handleActivatePet(pet.id); }} className="w-full text-xs py-1.5 rounded bg-green-500/20 text-green-400">
                          Set Active
                        </button>
                      )}
                      {!pet.evolved_to_mount && foods.length > 0 && (
                        <div>
                          <div className="text-[10px] text-forge-text-dim mb-1">Feed (prefers {pet.species.food_preference})</div>
                          <div className="flex flex-wrap gap-1">
                            {foods.map(f => (
                              <button
                                key={f.item.id}
                                onClick={(e) => { e.stopPropagation(); handleFeed(pet.id, f.item.id); }}
                                disabled={working}
                                className="text-xs px-2 py-1 rounded bg-forge-surface-alt hover:bg-forge-surface"
                                title={f.item.name}
                              >
                                {f.item.icon} x{f.quantity}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </Card>
              </motion.div>
            ))}
          </div>
        )
      )}

      {/* Mounts Tab */}
      {tab === 'mounts' && (
        mounts.length === 0 ? (
          <EmptyState>No mounts yet. Fully grow a pet to evolve it into a mount!</EmptyState>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
            {mounts.map(mount => (
              <motion.div key={mount.id} whileHover={{ y: -2 }}>
                <Card className={`cursor-pointer text-center ${mount.is_active ? 'ring-2 ring-amber-400' : ''}`}>
                  <div className="text-5xl mb-1">{mount.species.icon}</div>
                  <div className="text-xs font-medium">{mount.potion.name} {mount.species.name}</div>
                  <div className={`text-[10px] ${RARITY_COLORS[mount.potion.rarity]}`}>{mount.potion.rarity}</div>
                  <div className="text-[10px] text-amber-highlight mt-1">Mount</div>
                  {mount.is_active ? (
                    <div className="mt-1 text-[10px] text-amber-400 flex items-center justify-center gap-1">
                      <Crown size={10} /> Active
                    </div>
                  ) : (
                    <button onClick={() => handleActivateMount(mount.id)} className="mt-2 w-full text-xs py-1.5 rounded bg-amber-500/20 text-amber-400">
                      Set Active
                    </button>
                  )}
                </Card>
              </motion.div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
