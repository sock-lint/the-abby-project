import '../src/index.css';
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { MotionConfig } from 'framer-motion';
import AchievementCard from '../src/components/cards/AchievementCard';
import AchievementCardIcon from '../src/components/cards/AchievementCardIcon';
import Button from '../src/components/Button';
import BadgeSigil from '../src/components/atlas/BadgeSigil';
import SigilFrontispiece from '../src/pages/character/SigilFrontispiece';
import TrophyBadgePicker from '../src/pages/character/TrophyBadgePicker';
import ChallengeGoalCard from '../src/pages/trials/ChallengeGoalCard';
import RewardShop from '../src/pages/rewards/RewardShop';
import { SpriteCatalogContext } from '../src/providers/spriteCatalog.context';
import { applyTheme } from '../src/themes';

const params = new URLSearchParams(window.location.search);
applyTheme(params.get('theme') || 'hyrule');
if (params.get('large') === '1') {
  // Text grows independently of the canvas and safe-inset geometry. This
  // exercises wrapping more strictly than scaling the entire page together.
  const sizes = { micro: 20, tiny: 22, caption: 24, body: 28, lede: 36, sm: 28, base: 32, lg: 36, xl: 40, '2xl': 48, '3xl': 60, '4xl': 72 };
  for (const [token, size] of Object.entries(sizes)) {
    document.documentElement.style.setProperty(`--text-${token}`, `${size}px`);
    document.documentElement.style.setProperty(`--text-${token}--line-height`, '1.5');
  }
}
const long = params.get('long') === '1';
const description = 'Make a plan together, record each small step, and share what you learned with your family.';
const badges = [
  { id: 81, name: long ? 'ExtraordinarilyThoughtfulWoodlandGardenCreatorAndFamilyHelper' : 'Thoughtful creator', icon: '🦉', rarity: 'legendary', xp_bonus: 20, coin_bonus: 10, criterion_type: 'projects_completed', criterion_value: 1 },
  { id: 82, name: long ? 'ExtraordinarilyHelpfulProjectPlannerAndThoughtfulMaker' : 'Helpful planner', icon: '🌻', rarity: 'rare', xp_bonus: 30, criterion_type: 'projects_completed', criterion_value: 5 },
  { id: 83, name: long ? 'FutureWoodlandMasterpieceMakerAndThoughtfulGardenDesigner' : 'Future creator', icon: '🐚', rarity: 'epic', xp_bonus: 50, criterion_type: 'projects_completed', criterion_value: 10 },
];
const earnedBadges = badges.slice(0, 2).map(badge => ({ badge, earned_at: '2026-10-01T12:00:00Z' }));
const initialGoal = {
  id: 'synthetic-kit-goal', name: long ? 'BuildDocumentAndShareAMiniatureWoodlandGardenWithTheWholeFamily' : 'Build a woodland garden',
  description, what_counts: description, origin: 'automatic', status: 'active', pinned: false,
  progress: 3, target: 7, unit: 'activities', timezone: 'UTC',
  starts_at: '2026-10-12T00:00:00Z', ends_at: '2026-10-19T00:00:00Z',
  catalog_icon: 'challenge-hoard-builder',
  rewards: { coins: 20, xp: 30, items: [{ item_id: 401, item_name: 'Mega Hoard', item_catalog_icon: 'item-pouch-mega', item_sprite_key: 'retained-hoard', item_icon: '💎', quantity: 1 }] },
  action: { path: '/quests?tab=ventures', label: 'Open projects' },
};
const rewards = [
  { id: 21, name: long ? 'ChooseAFamilyMovieAndPlanTheEveningSnacksTogether' : 'Family movie night', description, cost_coins: 40, stock: 2, rarity: 'common', icon: '🎬', fulfillment_kind: 'real_world', is_active: true },
  { id: 22, name: long ? 'AnExtraordinarilyGenerousFishRewardForYourSavedCollection' : 'Fish reward', description, cost_coins: 80, stock: 3, rarity: 'rare', icon: '🐟', fulfillment_kind: 'digital_item', is_active: true,
    item_definition_detail: { name: 'Fish', catalog_icon: 'item-fish', sprite_key: 'retained-fish', icon: '🐟' } },
];
const sprites = {
  getSpriteMeta: key => ['retained-hoard', 'retained-fish'].includes(key) ? { url: `/synthetic/${key}.svg`, frames: 1 } : null,
  getSpriteUrl: key => `/synthetic/${key}.svg`,
};

export function Consumers() {
  const [event, setEvent] = useState('No action taken');
  const [currentTrophyId, setCurrentTrophyId] = useState(81);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [goal, setGoal] = useState(initialGoal);
  return <main className="mx-auto min-w-0 w-full max-w-6xl space-y-4 p-4 text-ink-primary" data-kit-fixture="consumers">
    <h1 className="font-body text-lede font-bold">Achievement card integration</h1>
    <p className="font-body text-caption">Local synthetic examples; no account reads, saves, rewards, or ownership changes.</p>
    <output className="block text-caption break-words" data-kit-event aria-live="polite">{event}</output>
    <section aria-label="Profile achievement">
      <SigilFrontispiece profile={{ display_name: long ? 'Avery, thoughtful maker and family helper' : 'Avery', active_title: { name: long ? 'ExtraordinarilyThoughtfulWoodlandProjectPlanner' : 'Thoughtful maker' }, level: 5, xp_in_level: 35, xp_needed_for_level: 100, login_streak: 4, longest_login_streak: 9, perfect_days_count: 2, active_trophy_badge: badges.find(badge => badge.id === currentTrophyId) || null }} onOpenTrophyPicker={() => setPickerOpen(true)} />
    </section>
    <section aria-label="Achievement collection" className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,180px),1fr))] gap-3">
      {badges.map((badge, index) => <BadgeSigil key={badge.id} badge={badge} earned={index < 2} earnedAt={index < 2 ? '2026-10-01T12:00:00Z' : null} hint={description} onSelect={({ badge: selected }) => setEvent(`View badge ${selected.id}`)} />)}
    </section>
    <section aria-label="Challenge cards" className="grid grid-cols-1 xl:grid-cols-2 gap-3">
      <ChallengeGoalCard goal={goal} timezone="UTC" onSelect={() => setEvent('View challenge')} onPin={() => { setGoal(previous => ({ ...previous, pinned: !previous.pinned })); setEvent(goal.pinned ? 'Unpin challenge' : 'Pin challenge'); }} />
      <ChallengeGoalCard goal={{ ...goal, id: 'synthetic-parent-goal', name: 'Parent goal', origin: 'parent' }} timezone="UTC" isParent onSelect={() => setEvent('View parent challenge')} />
    </section>
    <section aria-label="Reward cards">
      <RewardShop rewards={rewards} isParent={false} coinBalance={100} onRedeem={reward => setEvent(`Request reward ${reward.id}`)} onToggleWishlist={reward => setEvent(`Wishlist reward ${reward.id}`)} />
    </section>
    {pickerOpen && <TrophyBadgePicker allBadges={badges} earnedBadges={earnedBadges} currentTrophyId={currentTrophyId} onClose={() => setPickerOpen(false)} onSelect={id => { setCurrentTrophyId(id); setPickerOpen(false); setEvent(id === null ? 'Clear trophy' : `Choose trophy ${id}`); }} />}
  </main>;
}

export function Shapes() {
  const [event, setEvent] = useState('No action taken');
  return <main className="mx-auto min-w-0 max-w-5xl space-y-4 p-4 text-ink-primary" data-kit-fixture="shapes">
    <h1 className="font-body text-lede font-bold">Resizable card geometry</h1>
    <output data-kit-event className="block text-caption">{event}</output>
    {['wide', 'tall'].map(variant => <AchievementCard key={variant} variant={variant} data-kit-shape={variant} contentClassName="space-y-3">
      <h2 className="font-body text-lede font-bold break-words [overflow-wrap:anywhere]">{long ? 'ExtraordinarilyThoughtfulWoodlandGardenCreatorAndFamilyHelper' : `${variant} card`}</h2>
      <p className="font-body text-body">{description} {description} {description}</p>
      <Button onClick={() => setEvent(`Continue ${variant}`)}>Continue {variant}</Button>
    </AchievementCard>)}
  </main>;
}

export function Icons() {
  return <main className="mx-auto min-w-0 max-w-5xl space-y-4 p-4 text-ink-primary" data-kit-fixture="icons">
    <h1 className="font-body text-lede font-bold">Standalone generic icons</h1>
    <p className="font-body text-caption">These previews do not assign icons to existing badges or catalog records.</p>
    {[24, 32, 40, 64, 96].map(size => <section key={size} aria-label={`${size}px icons`} className="rounded-xl bg-ink-page-aged p-3 space-y-2">
      <h2 className="font-body text-body">{size} CSS pixels</h2>
      <div className="flex flex-wrap gap-4">{['book', 'heart', 'compass'].map(icon => <figure key={icon} className="space-y-1">
        <AchievementCardIcon icon={icon} size={size} label={`${icon} ${size}px`} />
        <figcaption className="font-body text-caption">{icon}</figcaption>
      </figure>)}</div>
    </section>)}
  </main>;
}

const mode = params.get('mode');
createRoot(document.getElementById('root')).render(<MemoryRouter><MotionConfig reducedMotion="always"><SpriteCatalogContext.Provider value={sprites}>
  {mode === 'icons' ? <Icons /> : mode === 'shapes' ? <Shapes /> : <Consumers />}
</SpriteCatalogContext.Provider></MotionConfig></MemoryRouter>);
