import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { MotionConfig } from 'framer-motion';
import HeroPrimaryCard from '../src/components/dashboard/HeroPrimaryCard';
import DailyChallengeCard from '../src/components/dashboard/DailyChallengeCard';
import PinnedChallengeCard from '../src/components/dashboard/PinnedChallengeCard';
import StarRating from '../src/components/StarRating';
import TrophySlot from '../src/pages/character/TrophySlot';
import ChallengeGoalCard from '../src/pages/trials/ChallengeGoalCard';
import ChallengesFolio from '../src/pages/trials/ChallengesFolio';
import PageShell from '../src/components/layout/PageShell';
import RewardShop from '../src/pages/rewards/RewardShop';
import PedestalImage from '../src/pedestal/PedestalImage';
import ParchmentCard from '../src/components/journal/ParchmentCard';
import EmptyState from '../src/components/EmptyState';
import FilteredEmptyState from '../src/components/FilteredEmptyState';
import Button from '../src/components/Button';
import BadgeSigil from '../src/components/atlas/BadgeSigil';
import BadgeDetailSheet from '../src/pages/achievements/BadgeDetailSheet';
import TrophyBadgePicker from '../src/pages/character/TrophyBadgePicker';
import SigilFrontispiece from '../src/pages/character/SigilFrontispiece';
import CoinBalanceCard from '../src/pages/rewards/CoinBalanceCard';
import AssignmentCard from '../src/pages/Homework/AssignmentCard';
import { SpriteCatalogContext } from '../src/providers/spriteCatalog.context';
import { applyTheme } from '../src/themes';
import { AuthProvider } from '../src/hooks/useApi';
import '../src/index.css';

const params = new URLSearchParams(window.location.search);
localStorage.setItem('abby_auth_token', 'synthetic-storybook-acceptance');
applyTheme(params.get('theme') || 'hyrule');
if (params.get('large') === '1') {
  // Enlarge type independently of artwork and layout dimensions. This is
  // deliberately stricter than scaling the entire layout with browser zoom.
  const sizes = { micro: 20, tiny: 22, caption: 24, body: 28, lede: 36, sm: 28, base: 32, lg: 36, xl: 40, '2xl': 48, '3xl': 60, '4xl': 72 };
  for (const [token, size] of Object.entries(sizes)) {
    document.documentElement.style.setProperty(`--text-${token}`, `${size}px`);
    document.documentElement.style.setProperty(`--text-${token}--line-height`, '1.5');
  }
}

const long = params.get('long') === '1';
const title = long ? 'Build, document, and share a miniature woodland garden with the whole family' : 'Build a woodland garden';
const description = long ? 'Take your time, make a plan together, and include a few notes about each small step so everyone can see what you learned along the way.' : 'One small step makes a good start.';
const badge = { id: 81, name: long ? 'ExtraordinarilyThoughtfulWoodlandGardenCreatorAndFamilyHelper' : 'Thoughtful creator', rarity: 'legendary', icon: '🏅' };
const syntheticGoal = {
  id: 'synthetic-storybook-goal', name: title, description, what_counts: description,
  origin: 'automatic', status: 'active', pinned: true,
  progress: 3, target: 7, unit: 'activities', timezone: 'UTC',
  starts_at: '2026-10-12T00:00:00Z', ends_at: '2026-10-19T00:00:00Z',
  rewards: { coins: 20, xp: 30, items: [] },
  action: { path: '/quests?tab=ventures', label: 'Open projects' },
};
const rewards = [
  { id: 21, name: long ? 'Choose a family movie and plan the evening snacks together' : 'Family movie night', description, cost_coins: 40, stock: 2, rarity: 'common', icon: '🎁', fulfillment_kind: 'real_world', is_active: true },
  { id: 22, name: 'Extra art time', description, cost_coins: 80, stock: 0, rarity: 'rare', icon: '🎨', fulfillment_kind: 'real_world', is_active: true },
];
const sprites = { getSpriteMeta: () => null, getSpriteUrl: () => null };
const starState = params.get('star-state') || 'missing';
// Two ordinary image records let the same component exercise loading/error
// placeholders even in public builds where purchased files are absent.
const syntheticStars = {
  release: {
    assets: ['star-lit', 'star-unlit'].map(id => ({ id, kind: 'image', variants: [{ id: 'web', file: `${id}.png` }] })),
    files: ['star-lit', 'star-unlit'].map(id => ({ path: `${id}.png`, media_type: 'image/png' })),
  },
  resolveUrl: file => `/synthetic/storybook-star-${file}`,
};

export function ComposedAccentsFixture() {
  const [event, setEvent] = useState('No action taken');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [currentTrophyId, setCurrentTrophyId] = useState(81);
  const [detail, setDetail] = useState(null);
  const badges = [
    { ...badge, criterion_type: 'projects_completed', criterion_value: 1, description, xp_bonus: 20 },
    { id: 82, name: long ? 'ExtraordinarilyHelpfulProjectPlannerAndThoughtfulMaker' : 'Helpful planner', rarity: 'rare', icon: '🦉', criterion_type: 'projects_completed', criterion_value: 5, description, xp_bonus: 40 },
    { id: 83, name: long ? 'FutureWoodlandMasterpieceMakerAndThoughtfulGardenDesigner' : 'Future creator', rarity: 'epic', icon: '🌿', criterion_type: 'projects_completed', criterion_value: 10, description, xp_bonus: 80 },
  ];
  const earnedBadges = badges.slice(0, 2).map(item => ({ badge: item, earned_at: '2026-10-01T12:00:00Z' }));
  const goals = [
    { ...syntheticGoal, id: 'synthetic-parent-a', origin: 'parent', pinned: false },
    { ...syntheticGoal, id: 'synthetic-parent-b', name: `Plan and share ${title.toLowerCase()}`, origin: 'parent', pinned: false },
  ];
  return <div className="min-h-screen bg-ink-page text-ink-primary" data-composed-ready>
    {/* The real shell reserves 240px for desktop navigation and 16/24px
        horizontal page padding. Keep its width contract around the real folio. */}
    <main className="ml-0 lg:ml-60 px-4 lg:px-6 pt-3">
      <PageShell animate={false}>
        <ChallengesFolio goals={goals} timezone="UTC" onSelect={() => {}} onPin={() => {}} />
        <output data-fixture-event className="block break-words text-caption" aria-live="polite">{event}</output>
        <section aria-label="Composed profile">
          <SigilFrontispiece profile={{ display_name: long ? 'A thoughtful woodland maker and family helper' : 'Synthetic maker', level: 5, xp_in_level: 35, xp_needed_for_level: 100, active_trophy_badge: badges.find(item => item.id === currentTrophyId) || null }} onOpenTrophyPicker={() => setPickerOpen(true)} />
        </section>
        <section aria-label="Badge collection" className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {badges.map((item, index) => <BadgeSigil key={item.id} badge={item} earned={index < 2} earnedAt={index < 2 ? '2026-10-01T12:00:00Z' : null} hint={description} onSelect={setDetail} />)}
        </section>
        <section aria-label="Shared empty states" className="space-y-4">
          <EmptyState>Nothing saved yet. {description}</EmptyState>
          <FilteredEmptyState query={title} onClear={() => setEvent('Clear synthetic filter')} />
        </section>
        <ParchmentCard flourish className="space-y-4" data-rhythm-panel>
          <h2 data-rhythm-child className="font-body font-bold text-lede">A shared panel with ordinary content flow</h2>
          <p data-rhythm-child className="font-body text-body">{description}</p>
          <Button data-rhythm-child className="block" onClick={() => setEvent('Continue synthetic panel')}>Continue</Button>
        </ParchmentCard>
        <ParchmentCard seal="top-right" className="py-3" data-decor-kind="seal"><h2 className="text-lede">A panel with custom vertical spacing</h2><p className="text-body">{description}</p></ParchmentCard>
        <ParchmentCard flourish seal="bottom-left" className="!p-4" data-decor-kind="combined"><h2 className="text-lede">A compact shared panel</h2><p className="text-body">{description}</p></ParchmentCard>
        <section aria-label="Parent Today"><HeroPrimaryCard role="parent" ctx={{ pendingCount: 3, hideDate: true }} /></section>
        <section aria-label="Composed rewards" className="space-y-4"><CoinBalanceCard coinBalance={50} isParent={false} onOpenExchange={() => setEvent('Open synthetic exchange')} /><RewardShop rewards={rewards} isParent={false} coinBalance={50} onRedeem={() => setEvent('Request synthetic reward')} /></section>
      </PageShell>
    </main>
    {pickerOpen && <TrophyBadgePicker allBadges={badges} earnedBadges={earnedBadges} currentTrophyId={currentTrophyId} onClose={() => setPickerOpen(false)} onSelect={(id) => { setCurrentTrophyId(id); setPickerOpen(false); setEvent(id === null ? 'Clear synthetic trophy' : `Choose synthetic trophy ${id}`); }} />}
    {detail && <BadgeDetailSheet entry={detail} allBadges={badges} earnedIds={new Set([81, 82])} onClose={() => setDetail(null)} />}
  </div>;
}

export function StorybookAccentsFixture() {
  const [event, setEvent] = useState('No action taken');
  const [goal, setGoal] = useState(syntheticGoal);
  const location = useLocation();
  const record = (name) => setEvent(name);
  const date = { weekday: 'Friday', dateStr: 'October 16' };
  const contexts = {
    idle: { ...date, idleTitle: title, idleDescription: description },
    clocked: { ...date, activeTimer: { project_title: title, elapsed_minutes: 32 } },
    'next-action': { ...date, nextAction: { kind: 'chore', id: 71, title, subtitle: description, icon: 'Sparkles', tone: 'moss' }, onCompleteChore: (id) => record(`Complete chore ${id}`) },
    'quest-progress': { ...date, activeQuest: { status: 'active', definition: { name: title }, current_progress: 3, effective_target: 7, progress_percent: 43 } },
  };
  return <main className="mx-auto min-w-0 max-w-5xl space-y-8 p-4 text-ink-primary">
    <h1 className="font-body font-bold text-lede">Storybook accents: synthetic component acceptance</h1>
    <p className="text-caption">Local examples use current app components, synthetic data, and no account requests.</p>
    <output className="block break-words text-caption" aria-live="polite" data-fixture-event>{event}</output>
    <output className="block break-words text-caption" data-fixture-location>{location.pathname}{location.search}</output>
    <div data-star-fallbacks className="flex items-center gap-2">
      {['star-lit', 'star-unlit'].map((assetId, index) => starState === 'missing'
        ? <PedestalImage key={assetId} assetId={assetId} staged={null} fallback={index ? '☆' : '★'} className="storybook-star text-gold-leaf" />
        : <PedestalImage key={assetId} assetId={assetId} staged={syntheticStars} fallback={index ? '☆' : '★'} className="storybook-star text-gold-leaf" />)}
    </div>
    {Object.entries(contexts).map(([variant, ctx]) => <section key={variant} aria-label={`Today ${variant}`} data-hero-variant={variant}>
      <HeroPrimaryCard role="child" ctx={ctx} />
    </section>)}
    <section aria-label="Daily bonus" className="space-y-4">
      {[false, true].map((awarded) => <DailyChallengeCard key={String(awarded)} challenge={{ date: '2026-10-16', goal: description, completed: awarded, awarded, progress_minutes: awarded ? 10 : 3, coin_reward: 10, xp_reward: 15, receipt_id: awarded ? 95 : null, coins_awarded: awarded ? 10 : 0, xp_awarded: awarded ? 15 : 0 }} />)}
      <p className="flex flex-wrap items-center gap-2 text-body">Project difficulty <StarRating value={3} /></p>
    </section>
    <section aria-label="Parent Today"><HeroPrimaryCard role="parent" ctx={{ ...date, pendingCount: 3 }} /></section>
    <section aria-label="Homework task"><AssignmentCard assignment={{ id: 72, title: 'Sketch', subject: 'art', due_date: null, effort_level: 3, description, submission_status: null, has_project: false }} onSubmit={() => record('Submit synthetic homework')} /></section>
    <section aria-label="Profile trophy" className="space-y-4">
      <div data-trophy-example="compact"><TrophySlot compact badge={badge} onOpen={() => record('Open compact trophy picker')} /></div>
      <div data-trophy-example="full"><TrophySlot badge={badge} onOpen={() => record('Open trophy picker')} /></div>
      <div data-trophy-example="empty"><TrophySlot compact badge={null} onOpen={() => record('Choose earned trophy')} /></div>
    </section>
    <section aria-label="Pinned challenge"><PinnedChallengeCard goal={goal} /></section>
    <section aria-label="Challenge card" className="grid grid-cols-1 xl:grid-cols-2"><ChallengeGoalCard goal={goal} timezone="UTC" onSelect={() => record('View synthetic challenge')} onPin={() => { setGoal({ ...goal, pinned: !goal.pinned }); record(goal.pinned ? 'Unpin synthetic challenge' : 'Pin synthetic challenge'); }} /></section>
    <section aria-label="Reward shop"><RewardShop rewards={rewards} isParent={false} coinBalance={50} pendingId={null} onRedeem={(reward) => record(`Request reward ${reward.id}`)} onToggleWishlist={(reward) => record(`Wishlist reward ${reward.id}`)} /></section>
  </main>;
}

createRoot(document.getElementById('root')).render(<MemoryRouter><MotionConfig reducedMotion="always"><AuthProvider><SpriteCatalogContext.Provider value={sprites}>{params.get('view') === 'composition' ? <ComposedAccentsFixture /> : <StorybookAccentsFixture />}</SpriteCatalogContext.Provider></AuthProvider></MotionConfig></MemoryRouter>);
