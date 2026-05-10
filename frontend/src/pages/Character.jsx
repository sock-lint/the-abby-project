import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  getCharacterProfile,
  getCosmetics,
  getCosmeticCatalog,
  getBadges,
  getAchievementsSummary,
  equipCosmetic,
  unequipCosmetic,
  setTrophyBadge,
} from '../api';
import { useApi, useAuth } from '../hooks/useApi';
import { normalizeList } from '../utils/api';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import EmptyState from '../components/EmptyState';
import SigilFrontispiece from './character/SigilFrontispiece';
import CosmeticChapter from './character/CosmeticChapter';
import TrophyBadgePicker from './character/TrophyBadgePicker';
import AdventuresEntry from './character/AdventuresEntry';
import WellbeingCard from './character/WellbeingCard';
import { COSMETIC_CHAPTERS } from './character/character.constants';

/**
 * Character (`/sigil`) — the Frontispiece. Thin orchestrator that merges
 * the character profile, owned cosmetics, the full cosmetic catalog,
 * and the earned/all badges feeds, then renders the hero frontispiece
 * above four cosmetic folios. Trophy picker is a BottomSheet mounted
 * under AnimatePresence so it can slide in and out without refetching.
 */
export default function Character() {
  const { user } = useAuth();
  const { data: profile, loading: loadingProfile, reload: reloadProfile } = useApi(getCharacterProfile);
  const { data: cosmetics, loading: loadingCosmetics, reload: reloadCosmetics } = useApi(getCosmetics);
  const { data: catalog, loading: loadingCatalog } = useApi(getCosmeticCatalog);
  const { data: allBadgesData, loading: loadingBadges } = useApi(getBadges);
  const { data: summary, loading: loadingSummary } = useApi(getAchievementsSummary);

  const [error, setError] = useState('');
  const [working, setWorking] = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  // Equip toast — `{ msg, key }`. The key bumps on each equip so the
  // toast re-animates even when the same slot is changed twice.
  const [equipToast, setEquipToast] = useState(null);

  // Auto-dismiss the equip toast after 3.2s.
  useEffect(() => {
    if (!equipToast) return undefined;
    const id = setTimeout(() => setEquipToast(null), 3200);
    return () => clearTimeout(id);
  }, [equipToast]);

  // Helper: find the cosmetic name we just equipped for the toast copy.
  const cosmeticName = (slot, itemId) => {
    const owned = cosmetics?.[slot] || [];
    const fromOwned = owned.find((c) => c.id === itemId);
    if (fromOwned) return fromOwned.name;
    const fromCatalog = (catalog?.[slot] || []).find((c) => c.id === itemId);
    return fromCatalog?.name || '';
  };

  const allBadges = useMemo(() => normalizeList(allBadgesData), [allBadgesData]);
  const earnedBadges = useMemo(() => summary?.badges_earned || [], [summary]);

  const anyLoading =
    loadingProfile || loadingCosmetics || loadingCatalog || loadingBadges || loadingSummary;

  if (anyLoading) return <Loader />;
  if (!profile) return <EmptyState>Unable to load sigil.</EmptyState>;

  const refresh = () => {
    reloadProfile();
    reloadCosmetics();
  };

  const handleEquip = async (itemId, slot) => {
    setWorking(itemId);
    setError('');
    try {
      await equipCosmetic(itemId);
      const name = cosmeticName(slot, itemId);
      setEquipToast({
        msg: name ? `Now wearing ${name}` : 'Cosmetic equipped',
        key: Date.now(),
      });
      refresh();
    } catch (e) { setError(e.message); }
    finally { setWorking(null); }
  };

  const handleUnequip = async (slot) => {
    setWorking(slot);
    setError('');
    try {
      await unequipCosmetic(slot);
      setEquipToast({ msg: 'Cosmetic unequipped', key: Date.now() });
      refresh();
    } catch (e) { setError(e.message); }
    finally { setWorking(null); }
  };

  const handleSelectTrophy = async (badgeId) => {
    setWorking('trophy');
    setError('');
    try {
      await setTrophyBadge(badgeId);
      reloadProfile();
      setPickerOpen(false);
    } catch (e) { setError(e.message); }
    finally { setWorking(null); }
  };

  const currentThemeName = user?.theme || 'hyrule';

  return (
    <div className="space-y-5 max-w-4xl mx-auto">
      <ErrorAlert message={error} />

      <AnimatePresence>
        {equipToast && (
          <motion.div
            key={equipToast.key}
            initial={{ y: -8, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: -8, opacity: 0 }}
            transition={{ duration: 0.2 }}
            role="status"
            aria-live="polite"
            className="fixed top-20 left-1/2 -translate-x-1/2 z-50 rounded-full bg-gold-leaf/90 text-ink-primary px-4 py-1.5 font-script text-sm shadow-lg"
          >
            {equipToast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      <SigilFrontispiece
        profile={profile}
        onOpenTrophyPicker={() => setPickerOpen(true)}
      />

      {user?.role !== 'parent' && <WellbeingCard />}

      <AdventuresEntry />

      <p className="font-script text-sm text-ink-whisper text-center max-w-xl mx-auto">
        your inside-cover plate · choose a trophy seal you've earned, equip cosmetics from the four chapters below
      </p>

      <div className="space-y-4">
        {COSMETIC_CHAPTERS.map((chapter) => (
          <CosmeticChapter
            key={chapter.slot}
            chapter={chapter}
            owned={cosmetics?.[chapter.slot] || []}
            catalog={catalog?.[chapter.slot] || []}
            activeId={profile[chapter.slot]?.id || null}
            currentThemeName={currentThemeName}
            busy={working}
            onEquip={(itemId) => handleEquip(itemId, chapter.slot)}
            onUnequip={handleUnequip}
          />
        ))}
      </div>

      <AnimatePresence>
        {pickerOpen && (
          <TrophyBadgePicker
            allBadges={allBadges}
            earnedBadges={earnedBadges}
            currentTrophyId={profile.active_trophy_badge?.id || null}
            onSelect={handleSelectTrophy}
            onClose={() => setPickerOpen(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}
