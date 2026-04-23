import { useMemo, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
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

  const handleEquip = async (itemId) => {
    setWorking(itemId);
    setError('');
    try {
      await equipCosmetic(itemId);
      refresh();
    } catch (e) { setError(e.message); }
    finally { setWorking(null); }
  };

  const handleUnequip = async (slot) => {
    setWorking(slot);
    setError('');
    try {
      await unequipCosmetic(slot);
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

      <SigilFrontispiece
        profile={profile}
        onOpenTrophyPicker={() => setPickerOpen(true)}
      />

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
            onEquip={handleEquip}
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
