import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Crown, Star } from 'lucide-react';
import { getStable, getInventory, feedPet, activatePet } from '../../../api';
import { useApi } from '../../../hooks/useApi';
import Loader from '../../../components/Loader';
import EmptyState from '../../../components/EmptyState';
import ErrorAlert from '../../../components/ErrorAlert';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import IncipitBand from '../../../components/atlas/IncipitBand';
import TomeShelf from '../../../components/atlas/TomeShelf';
import { EggIcon } from '../../../components/icons/JournalIcons';
import RpgSprite from '../../../components/rpg/RpgSprite';
import { normalizeList } from '../../../utils/api';
import { RARITY_TEXT_COLORS } from '../../../constants/colors';
import { RARITY_HALO, PROGRESS_TIER } from '../../../components/atlas/mastery.constants';
import { COMPANION_FILTERS, HAPPINESS_WHISPER, compareByRarityThenName } from './party.constants';
import PetCeremonyModal from '../PetCeremonyModal';

/**
 * Companions — owned, unevolved pets. Lifted from the old Stable.jsx
 * "pets" branch and given filter pills (All / Active / Hungry / Ready
 * to evolve) so a roster of dozens stays navigable.
 */
export default function Companions() {
  const { data: stableData, loading: loadingStable, reload: reloadStable } = useApi(getStable);
  const { data: inventoryData, loading: loadingInventory, reload: reloadInventory } = useApi(getInventory);
  const [filter, setFilter] = useState('all');
  const [error, setError] = useState('');
  const [selectedPet, setSelectedPet] = useState(null);
  const [working, setWorking] = useState(false);
  const [evolveCeremony, setEvolveCeremony] = useState(null);

  const pets = useMemo(() => stableData?.pets || [], [stableData]);
  const totalPossible = stableData?.total_possible || 0;
  const inventory = normalizeList(inventoryData);
  const foods = inventory.filter((e) => e.item.item_type === 'food');

  const counts = useMemo(() => {
    const out = {};
    COMPANION_FILTERS.forEach((f) => {
      out[f.key] = pets.filter(f.match).length;
    });
    return out;
  }, [pets]);

  const visiblePets = useMemo(() => {
    const f = COMPANION_FILTERS.find((x) => x.key === filter) || COMPANION_FILTERS[0];
    return [...pets.filter(f.match)].sort(compareByRarityThenName);
  }, [pets, filter]);

  if (loadingStable || loadingInventory) return <Loader />;

  const refresh = () => { reloadStable(); reloadInventory(); };

  const handleFeed = async (pet, foodItemId) => {
    setWorking(true);
    setError('');
    try {
      const result = await feedPet(pet.id, foodItemId);
      setSelectedPet(null);
      if (result?.evolved) {
        setEvolveCeremony({ species: pet.species, potion: pet.potion });
      }
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

  return (
    <div className="space-y-6">
      {evolveCeremony && (
        <PetCeremonyModal
          mode="evolve"
          species={evolveCeremony.species}
          potion={evolveCeremony.potion}
          onDismiss={() => setEvolveCeremony(null)}
        />
      )}
      <IncipitBand
        letter="C"
        title="Companions"
        kicker="· your party · companions you've raised ·"
        meta={
          <>
            <span className="tabular-nums">{pets.length} of {totalPossible}</span>
            <span>hatched</span>
          </>
        }
        progressPct={totalPossible ? (pets.length / totalPossible) * 100 : 0}
      />

      <p className="font-script text-sm text-ink-whisper -mt-2 max-w-xl">
        feed companions to grow them — at full bloom they evolve into mounts you can ride
      </p>

      <ErrorAlert message={error} />

      {pets.length > 0 && (
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

      {pets.length === 0 ? (
        <EmptyState icon={<EggIcon size={36} />}>
          No companions yet. Find eggs and potions in drops, then cast the ritual.
        </EmptyState>
      ) : visiblePets.length === 0 ? (
        <EmptyState icon={<EggIcon size={28} />}>
          No companions match this filter.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {visiblePets.map((pet) => (
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
                  <div className="flex items-center justify-center h-16 mb-1">
                    <div
                      className={`relative inline-flex items-center justify-center rounded-full p-1 bg-ink-page-aged/40 ${
                        RARITY_HALO[pet.potion.rarity] || RARITY_HALO.common
                      }`}
                    >
                      <RpgSprite
                        spriteKey={pet.species.sprite_key}
                        icon={pet.species.icon}
                        size={56}
                        alt={`${pet.potion.name} ${pet.species.name}`}
                        potionSlug={pet.potion.slug}
                        dim={
                          pet.evolved_to_mount
                            ? null
                            : pet.happiness_level && pet.happiness_level !== 'happy'
                              ? pet.happiness_level
                              : null
                        }
                      />
                    </div>
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
                  {!pet.evolved_to_mount && HAPPINESS_WHISPER[pet.happiness_level] && (
                    <div className="font-script text-tiny text-ink-whisper italic mt-0.5">
                      {HAPPINESS_WHISPER[pet.happiness_level]}
                    </div>
                  )}
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
                              onClick={(e) => { e.stopPropagation(); handleFeed(pet, f.item.id); }}
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
      )}
    </div>
  );
}
