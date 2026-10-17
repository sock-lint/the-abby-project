import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { MotionConfig } from 'framer-motion';
import SigilFrontispiece from '../src/pages/character/SigilFrontispiece';
import CosmeticChapter from '../src/pages/character/CosmeticChapter';
import TrophyBadgePicker from '../src/pages/character/TrophyBadgePicker';
import { COSMETIC_CHAPTERS } from '../src/pages/character/character.constants';
import PageShell from '../src/components/layout/PageShell';
import { SpriteCatalogContext } from '../src/providers/spriteCatalog.context';
import { AuthProvider } from '../src/hooks/useApi';
import { applyTheme } from '../src/themes';
import catalogFixture from '../../contracts/api/fixtures/profile-card-styles-catalog.json';
import ownedFixture from '../../contracts/api/fixtures/profile-card-styles-owned.json';
import profileFixture from '../../contracts/api/fixtures/profile-card-style-character.json';
import '../src/index.css';

const params = new URLSearchParams(window.location.search);
const theme = params.get('theme') || 'hyrule';
const long = params.get('long') === '1';
localStorage.setItem('abby_auth_token', 'synthetic-profile-card-styles');
applyTheme(theme);
if (params.get('large') === '1') {
  const sizes = { micro: 20, tiny: 22, caption: 24, body: 28, lede: 36, sm: 28, base: 32, lg: 36, xl: 40, '2xl': 48, '3xl': 60, '4xl': 72 };
  for (const [token, size] of Object.entries(sizes)) {
    document.documentElement.style.setProperty(`--text-${token}`, `${size}px`);
    document.documentElement.style.setProperty(`--text-${token}--line-height`, '1.5');
  }
}
const frames = catalogFixture.active_frame.map(item => ({
  ...item,
  name: long ? `${item.name}—ExtraordinarilyThoughtfulWoodlandGardenCreatorAndFamilyHelper` : item.name,
  description: item.description || 'Earn this reward through projects, activities, or a qualifying challenge.',
}));
const ownedIds = params.get('owned') === 'all'
  ? frames.map(item => item.id) : ownedFixture.active_frame.map(item => item.id);
const owned = frames.filter(item => ownedIds.includes(item.id));
const initialFrameId = { nature: 401, light: 402, legacy: 403, none: null }[params.get('frame') || 'nature'];
const badges = [
  { id: 81, name: long ? 'ExtraordinarilyThoughtfulWoodlandGardenCreatorAndFamilyHelper' : 'Thoughtful creator', rarity: 'legendary', icon: '🏅', criterion_type: 'projects_completed', criterion_value: 1, description: 'Share a completed project.', xp_bonus: 20 },
  { id: 82, name: long ? 'ExtraordinarilyHelpfulProjectPlannerAndThoughtfulMaker' : 'Helpful planner', rarity: 'rare', icon: '🦉', criterion_type: 'projects_completed', criterion_value: 5, description: 'Plan several projects.', xp_bonus: 40 },
  { id: 83, name: 'Future garden designer', rarity: 'epic', icon: '🌿', criterion_type: 'projects_completed', criterion_value: 10, description: 'Keep learning.', xp_bonus: 80 },
];
const earnedBadges = badges.slice(0, 2).map(badge => ({ badge, earned_at: '2026-10-01T12:00:00Z' }));
const sprites = { getSpriteMeta: () => null, getSpriteUrl: () => null };

export function ProfileCardStylesFixture() {
  const [activeFrameId, setActiveFrameId] = useState(initialFrameId);
  const [activeBadgeId, setActiveBadgeId] = useState(81);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [event, setEvent] = useState('No action taken');
  const activeFrame = frames.find(item => item.id === activeFrameId) || null;
  const badge = badges.find(item => item.id === activeBadgeId) || null;
  const profile = { ...profileFixture, display_name: 'Avery', level: 5, xp_in_level: 35, xp_needed_for_level: 100, login_streak: 7, longest_login_streak: 12, perfect_days_count: 4, active_frame: activeFrame, active_trophy_badge: badge };
  return <div className="min-h-screen bg-ink-page text-ink-primary">
    <main className="ml-0 px-4 pt-3 lg:ml-60 lg:px-6" data-profile-card-styles-ready>
      <PageShell width="narrow" animate={false}>
        <output className="block break-words text-caption" aria-live="polite" data-fixture-event>{event}</output>
        <section aria-label="Profile frontispiece"><SigilFrontispiece profile={profile} onOpenTrophyPicker={() => setPickerOpen(true)} /></section>
        <CosmeticChapter chapter={COSMETIC_CHAPTERS.find(chapter => chapter.slot === 'active_frame')}
          owned={owned} catalog={frames} activeId={activeFrameId} currentThemeName={theme}
          onEquip={id => {
            setEvent(`Equip synthetic frame ${id}`);
            if (!ownedIds.includes(id)) throw new Error('A locked frame invoked its equip callback.');
            setActiveFrameId(id);
          }}
          onUnequip={slot => { setEvent(`Remove synthetic frame ${slot}`); setActiveFrameId(null); }} />
      </PageShell>
    </main>
    {pickerOpen && <TrophyBadgePicker allBadges={badges} earnedBadges={earnedBadges} currentTrophyId={activeBadgeId}
      onClose={() => setPickerOpen(false)} onSelect={id => {
        setActiveBadgeId(id); setPickerOpen(false); setEvent(id === null ? 'Clear synthetic trophy' : `Choose synthetic trophy ${id}`);
      }} />}
  </div>;
}

createRoot(document.getElementById('root')).render(<MemoryRouter><MotionConfig reducedMotion="always"><AuthProvider><SpriteCatalogContext.Provider value={sprites}><ProfileCardStylesFixture /></SpriteCatalogContext.Provider></AuthProvider></MotionConfig></MemoryRouter>);
