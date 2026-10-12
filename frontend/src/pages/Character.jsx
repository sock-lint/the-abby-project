import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Link } from 'react-router-dom';
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
import Button from '../components/Button';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import EmptyState from '../components/EmptyState';
import PageShell from '../components/layout/PageShell';
import TomeShelf from '../components/atlas/TomeShelf';
import { applyTheme } from '../themes';
import { tierForProgress } from '../components/atlas/mastery.constants';
import SigilFrontispiece from './character/SigilFrontispiece';
import CosmeticChapter from './character/CosmeticChapter';
import TrophyBadgePicker from './character/TrophyBadgePicker';
import AdventuresEntry from './character/AdventuresEntry';
import WellbeingCard from './character/WellbeingCard';
import CompanionPanel from '../components/companion/CompanionPanel';
import {
  COSMETIC_CHAPTERS,
  mergeSlotCosmetics,
} from './character/character.constants';

const ACTIVE_CHAPTER_KEY = 'atlas:sigil-frontispiece:active-chapter';

/**
 * Character (`/sigil`) — the Frontispiece. Thin orchestrator that merges
 * the character profile, owned cosmetics, the full cosmetic catalog,
 * and the earned/all badges feeds, then renders the hero frontispiece
 * above four cosmetic folios. Trophy picker is a BottomSheet mounted
 * under AnimatePresence so it can slide in and out without refetching.
 */
export default function Character() {
  const { user, setUser } = useAuth();
  const {
    data: profile, loading: loadingProfile, error: profileError,
    reload: reloadProfile, setData: setProfileData,
  } = useApi(getCharacterProfile);
  const {
    data: cosmetics, loading: loadingCosmetics, error: cosmeticsError, reload: reloadCosmetics,
  } = useApi(getCosmetics);
  const { data: catalog, loading: loadingCatalog, error: catalogError, reload: reloadCatalog } = useApi(getCosmeticCatalog);
  const { data: allBadgesData, loading: loadingBadges, error: badgesError, reload: reloadBadges } = useApi(getBadges);
  const { data: summary, loading: loadingSummary, error: summaryError, reload: reloadSummary } = useApi(getAchievementsSummary);

  const [error, setError] = useState('');
  const [working, setWorking] = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  // Equip toast — `{ msg, key }`. The key bumps on each equip so the
  // toast re-animates even when the same slot is changed twice.
  const [equipToast, setEquipToast] = useState(null);
  const [activeChapterSlot, setActiveChapterSlot] = useState(() => {
    try {
      return window.localStorage?.getItem(ACTIVE_CHAPTER_KEY) || COSMETIC_CHAPTERS[0].slot;
    } catch {
      return COSMETIC_CHAPTERS[0].slot;
    }
  });

  useEffect(() => {
    if (!activeChapterSlot) return;
    try {
      window.localStorage?.setItem(ACTIVE_CHAPTER_KEY, activeChapterSlot);
    } catch {
      // ignore quota / disabled storage
    }
  }, [activeChapterSlot]);

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

  // Hoist mergeSlotCosmetics: compute owned/total per chapter once so the
  // collection cards and the active chapter share counts without re-walking the
  // catalog four times. Memoized BEFORE the early-return guards so the hook
  // order stays stable across loading / loaded renders.
  const chapterEntriesBySlot = useMemo(() => {
    const out = {};
    for (const chapter of COSMETIC_CHAPTERS) {
      out[chapter.slot] = mergeSlotCosmetics(
        chapter.slot,
        cosmetics?.[chapter.slot] || [],
        catalog?.[chapter.slot] || [],
        profile?.[chapter.slot]?.id || null,
      );
    }
    return out;
  }, [cosmetics, catalog, profile]);

  const anyLoading =
    loadingProfile || loadingCosmetics || loadingCatalog || loadingBadges || loadingSummary;
  const loadError =
    profileError || cosmeticsError || catalogError || badgesError || summaryError;

  if (anyLoading) return <Loader />;
  if (loadError) {
    return (
      <div className="space-y-3 max-w-xl mx-auto">
        <ErrorAlert message={loadError || 'Could not load your profile.'} />
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            reloadProfile();
            reloadCosmetics();
            reloadCatalog();
            reloadBadges();
            reloadSummary();
          }}
        >
          Try again
        </Button>
      </div>
    );
  }
  if (!profile) return <EmptyState>Unable to load profile.</EmptyState>;

  const refresh = () => {
    reloadProfile();
    reloadCosmetics();
  };

  // Resolve the cosmetic record we're about to equip from owned or catalog,
  // so the optimistic profile-state update has a real {id, name, ...} object
  // to slot in rather than a bare id.
  const findCosmetic = (slot, itemId) => {
    const owned = cosmetics?.[slot] || [];
    const fromOwned = owned.find((c) => c.id === itemId);
    if (fromOwned) return fromOwned;
    const fromCatalog = (catalog?.[slot] || []).find((c) => c.id === itemId);
    return fromCatalog || { id: itemId };
  };

  const handleEquip = async (itemId, slot) => {
    setWorking(itemId);
    setError('');
    const previous = profile[slot] || null;
    const next = findCosmetic(slot, itemId);
    // Optimistic: reflect the new equip immediately so the tile flips
    // states without waiting for the round-trip + refetch.
    setProfileData({ ...profile, [slot]: next });
    try {
      await equipCosmetic(itemId);
      // Equipping a journal cover writes `User.theme` server-side
      // (CosmeticService.equip), so mirror it locally: paint the cover AND
      // move the auth user. Without the second half, `currentThemeName` below
      // still reads the OLD cover, and CosmeticSigil's mouseleave — which on a
      // phone fires on the next tap anywhere — repainted the page back to it,
      // making a successful equip look like it silently failed.
      const themeSlug = slot === 'active_theme' ? next?.metadata?.theme : null;
      if (themeSlug) {
        applyTheme(themeSlug);
        if (user) setUser({ ...user, theme: themeSlug });
      }
      const name = next?.name || cosmeticName(slot, itemId);
      setEquipToast({
        msg: name ? `Now wearing ${name}` : 'Cosmetic equipped',
        key: Date.now(),
      });
      refresh();
    } catch (e) {
      // Rollback to whatever was equipped (or null) before the click.
      setProfileData({ ...profile, [slot]: previous });
      setError(e.message);
    } finally { setWorking(null); }
  };

  const handleUnequip = async (slot) => {
    setWorking(slot);
    setError('');
    const previous = profile[slot] || null;
    setProfileData({ ...profile, [slot]: null });
    try {
      await unequipCosmetic(slot);
      setEquipToast({ msg: 'Cosmetic unequipped', key: Date.now() });
      refresh();
    } catch (e) {
      setProfileData({ ...profile, [slot]: previous });
      setError(e.message);
    } finally { setWorking(null); }
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

  const shelfItems = COSMETIC_CHAPTERS.map((chapter) => {
    const entries = chapterEntriesBySlot[chapter.slot] || [];
    const owned = entries.filter((e) => e.owned).length;
    const total = entries.length;
    const pct = total ? (owned / total) * 100 : 0;
    return {
      id: chapter.slot,
      name: chapter.name,
      icon: chapter.letter,
      chip: `${owned}/${total}`,
      progressPct: pct,
      tier: tierForProgress({ unlocked: true, progressPct: pct, level: 0 }),
      ariaLabel: `${chapter.name}, ${owned} of ${total} owned`,
    };
  });

  const activeChapter =
    COSMETIC_CHAPTERS.find((c) => c.slot === activeChapterSlot) || COSMETIC_CHAPTERS[0];

  return (
    <PageShell width="narrow">
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
            className="fixed top-20 left-1/2 -translate-x-1/2 z-50 rounded-full bg-gold-leaf/90 text-ink-primary px-4 py-1.5 font-body font-semibold text-body shadow-lg"
          >
            {equipToast.msg}
          </motion.div>
        )}
      </AnimatePresence>

      <SigilFrontispiece
        profile={profile}
        onOpenTrophyPicker={() => setPickerOpen(true)}
      />

      <div className="flex flex-wrap justify-center gap-x-6 gap-y-2 text-body font-semibold text-sheikah-teal-deep">
        <Link className="inline-flex min-h-11 items-center underline underline-offset-4" to="/settings">Edit account & settings</Link>
        <Link className="inline-flex min-h-11 items-center underline underline-offset-4" to="/bestiary">My pets</Link>
      </div>

      <CompanionPanel />

      {user?.role === 'child' && <WellbeingCard />}

      <AdventuresEntry />

      <p className="font-body text-body text-ink-secondary text-center leading-relaxed max-w-xl mx-auto">
        Make this profile yours. Choose an earned badge for your trophy, then personalize your look with the four collections below.
      </p>

      <TomeShelf
        items={shelfItems}
        activeId={activeChapter.slot}
        onSelect={setActiveChapterSlot}
        ariaLabel="Profile collections"
      />

      <CosmeticChapter
        key={activeChapter.slot}
        chapter={activeChapter}
        owned={cosmetics?.[activeChapter.slot] || []}
        catalog={catalog?.[activeChapter.slot] || []}
        activeId={profile[activeChapter.slot]?.id || null}
        currentThemeName={currentThemeName}
        busy={working}
        onEquip={(itemId) => handleEquip(itemId, activeChapter.slot)}
        onUnequip={handleUnequip}
      />

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
    </PageShell>
  );
}
