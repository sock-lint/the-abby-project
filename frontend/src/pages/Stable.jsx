import { useState } from 'react';
import { motion } from 'framer-motion';
import { Crown, Star } from 'lucide-react';
import { getStable, getInventory, feedPet, activatePet, activateMount } from '../api';
import { useApi } from '../hooks/useApi';
import Loader from '../components/Loader';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import DeckleDivider from '../components/journal/DeckleDivider';
import { EggIcon, DragonIcon } from '../components/icons/JournalIcons';
import RpgSprite from '../components/rpg/RpgSprite';
import { normalizeList } from '../utils/api';
import { RARITY_TEXT_COLORS } from '../constants/colors';

/**
 * Stable / Party — owned companions and mounts.
 *
 * Hatch + Breed live on the dedicated Hatchery tab now (see
 * pages/bestiary/hatchery/Hatchery.jsx). When mounted inside a hub that
 * exposes that tab separately, callers should leave hatch/breed off this
 * page entirely; nothing on Stable currently re-shows them, but the
 * data fetches stay so the food picker continues to work.
 */
export default function Stable() {
  const { data: stableData, loading: loadingStable, reload: reloadStable } = useApi(getStable);
  const { data: inventoryData, loading: loadingInventory, reload: reloadInventory } = useApi(getInventory);
  const [tab, setTab] = useState('pets');
  const [error, setError] = useState('');
  const [selectedPet, setSelectedPet] = useState(null);
  const [working, setWorking] = useState(false);

  if (loadingStable || loadingInventory) return <Loader />;

  const pets = stableData?.pets || [];
  const mounts = stableData?.mounts || [];
  const totalPossible = stableData?.total_possible || 0;

  const inventory = normalizeList(inventoryData);
  const foods = inventory.filter((e) => e.item.item_type === 'food');

  const refresh = () => { reloadStable(); reloadInventory(); };

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
    setWorking(true);
    setError('');
    try { await activatePet(petId); refresh(); }
    catch (e) { setError(e.message); }
    finally { setWorking(false); }
  };

  const handleActivateMount = async (mountId) => {
    setWorking(true);
    setError('');
    try { await activateMount(mountId); refresh(); }
    catch (e) { setError(e.message); }
    finally { setWorking(false); }
  };

  return (
    <div className="space-y-6">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base">
          the party · companions and mounts you've raised
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Party
        </h1>
        <div className="font-script text-sm text-ink-whisper mt-1 max-w-xl">
          feed companions to grow them — at full bloom they evolve into mounts you can ride · hatch and breed live on the Hatchery tab
        </div>
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
                    <div className="flex items-center justify-center h-14 mb-1">
                      <RpgSprite
                        spriteKey={pet.species.sprite_key}
                        icon={pet.species.icon}
                        size={56}
                        alt={`${pet.potion.name} ${pet.species.name}`}
                        potionSlug={pet.potion.slug}
                      />
                    </div>
                    <div className="font-body text-sm font-medium leading-tight">
                      {pet.potion.name} {pet.species.name}
                    </div>
                    <div
                      className={`font-script text-tiny uppercase tracking-wider ${
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
                        <div className="font-rune text-micro text-ink-whisper mt-0.5">
                          {pet.growth_points}/100
                        </div>
                      </div>
                    )}
                    {pet.evolved_to_mount && (
                      <div className="mt-1 font-script text-tiny text-gold-leaf flex items-center justify-center gap-1">
                        <Crown size={10} /> evolved
                      </div>
                    )}
                    {pet.is_active && (
                      <div className="mt-1 font-script text-tiny text-moss flex items-center justify-center gap-1">
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
                          disabled={working}
                          className="w-full font-body text-xs py-1.5 rounded-lg bg-moss/20 text-moss border border-moss/50 hover:bg-moss/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {working ? 'Setting…' : 'Set active'}
                        </button>
                      )}
                      {!pet.evolved_to_mount && pet.species.slug === 'companion' && (
                        <div className="font-script text-tiny text-ink-whisper italic">
                          grows on its own — every daily check-in adds a little
                        </div>
                      )}
                      {!pet.evolved_to_mount && foods.length > 0 && (
                        <div>
                          <div className="font-script text-tiny text-ink-whisper mb-1">
                            feed{pet.species.food_preference ? ` · prefers ${pet.species.food_preference}` : ''}
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {foods.map((f) => (
                              <button
                                key={f.item.id}
                                type="button"
                                onClick={(e) => { e.stopPropagation(); handleFeed(pet.id, f.item.id); }}
                                disabled={working}
                                title={f.item.name}
                                className="font-body text-xs px-2 py-1 rounded bg-ink-page border border-ink-page-shadow hover:border-sheikah-teal/50 transition-colors flex items-center gap-1"
                              >
                                <RpgSprite
                                  spriteKey={f.item.sprite_key}
                                  icon={f.item.icon}
                                  size={24}
                                  alt={f.item.name}
                                />
                                ×{f.quantity}
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
