import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Link, useNavigate } from 'react-router-dom';
import { Crown, Star } from 'lucide-react';
import { getStable, getInventory, feedPet, activatePet } from '../../../api';
import { useApi } from '../../../hooks/useApi';
import Loader from '../../../components/Loader';
import EmptyState from '../../../components/EmptyState';
import ErrorAlert from '../../../components/ErrorAlert';
import Button from '../../../components/Button';
import BottomSheet from '../../../components/BottomSheet';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import IncipitBand from '../../../components/atlas/IncipitBand';
import TomeShelf from '../../../components/atlas/TomeShelf';
import { EggIcon } from '../../../components/icons/JournalIcons';
import RpgSprite from '../../../components/rpg/RpgSprite';
import { petSpriteKeys } from '../../../components/rpg/petSpriteKeys';
import { normalizeList } from '../../../utils/api';
import { RARITY_TEXT_COLORS } from '../../../constants/colors';
import { RARITY_HALO, PROGRESS_TIER } from '../../../components/atlas/mastery.constants';
import { COMPANION_FILTERS, HAPPINESS_WHISPER, compareByRarityThenName } from './party.constants';
import PetCeremonyModal from '../PetCeremonyModal';
import CompanionPreview from '../../../components/companion/CompanionPreview';

/**
 * Companions — owned, unevolved pets. Lifted from the old Stable.jsx
 * "pets" branch and given filter pills (All / Active / Hungry / Ready
 * to evolve) so a roster of dozens stays navigable.
 */
export default function Companions() {
  const navigate = useNavigate();
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

  const pets = useMemo(() => stableData?.pets || [], [stableData]);
  const totalPossible = stableData?.total_possible || 0;
  const inventory = normalizeList(inventoryData);
  const foods = inventory.filter((e) => e.item.item_type === 'food' && e.quantity > 0);

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
  const homePet = pets.find((pet) => pet.id === viewPetId) || pets.find((pet) => pet.is_active) || pets[0];
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
      {homePet && <CompanionPreview
        variant="primary"
        creature={homePet}
        kicker="At home in your woodland"
        summary={homePet.evolved_to_mount ? 'Your companion has grown. There are new places to explore together.' : 'A little care today, a little more growth. Choose something from your food collection.'}
        onInteract={() => homePet.evolved_to_mount ? navigate(explorePath) : setSelectedPet(homePet)}
        interactionLabel={`${homePet.evolved_to_mount ? 'Explore' : 'Spend time'} with ${homePet.name?.trim() || homePet.species.name}`}
      >
        <div className="companion-preview-actions">
          <Button onClick={() => homePet.evolved_to_mount ? navigate(explorePath) : setSelectedPet(homePet)}>{homePet.evolved_to_mount ? 'Go exploring' : 'Feed your companion'}</Button>
          <Link className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep" to="/bestiary?tab=hatchery">Hatch a pet →</Link>
        </div>
      </CompanionPreview>}

      <IncipitBand
        letter="C"
        title="Companions"
        kicker="The pets you've hatched"
        meta={
          <>
            <span className="tabular-nums">{pets.length} of {totalPossible}</span>
            <span>hatched</span>
          </>
        }
        progressPct={totalPossible ? (pets.length / totalPossible) * 100 : 0}
      />

      <p className="font-script text-body text-ink-whisper -mt-2 max-w-xl">
        Feed companions to help them grow. At 100 growth, they evolve into mounts you can ride.
      </p>

      {/* Covers the partial case too: stable loaded but the satchel fetch
          failed, which would otherwise just hide the feed chips. */}
      <ErrorAlert message={error || fetchError} />

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
          No companions yet. Collect an egg and a potion, then combine them on the Hatching tab.
        </EmptyState>
      ) : visiblePets.length === 0 ? (
        <EmptyState icon={<EggIcon size={28} />}>
          No companions match this filter.
        </EmptyState>
      ) : (
        <div role="list" aria-label="Your companions" className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {visiblePets.map((pet) => (
            <motion.div key={pet.id} role="listitem" whileHover={{ y: -2 }}>
              <ParchmentCard
                className={`transition-all ${
                  pet.is_active
                    ? `ring-2 ring-offset-2 ring-offset-ink-page ring-moss`
                    : ''
                }`}
              >
                <button
                  type="button"
                  className="w-full rounded-lg text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep"
                  aria-label={`Care for ${pet.potion.name} ${pet.species.name}`}
                  aria-expanded={selectedPet?.id === pet.id}
                  onClick={() => { setViewPetId(pet.id); setSelectedPet(pet); }}
                >
                  <div className="flex items-center justify-center h-16 mb-1">
                    <div
                      className={`relative inline-flex items-center justify-center rounded-full p-1 bg-ink-page-aged/40 ${
                        RARITY_HALO[pet.potion.rarity] || RARITY_HALO.common
                      }`}
                    >
                      <RpgSprite
                        {...petSpriteKeys(pet)}
                        icon={pet.species.icon}
                        size={56}
                        className="rounded-full"
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
                  <div className="font-body text-body font-medium leading-tight break-words">
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
                </button>

              </ParchmentCard>
            </motion.div>
          ))}
        </div>
      )}
      {carePet && (
        <BottomSheet title={`Care for ${carePet.name?.trim() || `${carePet.potion.name} ${carePet.species.name}`}`} onClose={() => setSelectedPet(null)} disabled={working}>
          <ErrorAlert message={error || inventoryError} onRetry={inventoryError ? reloadInventory : undefined} />
          <p className="text-body text-ink-secondary mb-3">{carePet.evolved_to_mount ? 'Your companion is fully grown. Visit Mounts to explore and collect expedition rewards.' : `${carePet.growth_points}/100 growth${carePet.species.food_preference ? ` · Prefers ${carePet.species.food_preference}` : ''}`}</p>
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
                    <RpgSprite
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
