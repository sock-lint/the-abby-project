import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, useLocation } from 'react-router-dom';
import '../src/index.css';
import { applyTheme } from '../src/themes';
import { AuthProvider } from '../src/hooks/useApi';
import { SpriteCatalogContext } from '../src/providers/spriteCatalog.context';
import BadgeSigil from '../src/components/atlas/BadgeSigil';
import BadgeDetailSheet from '../src/pages/achievements/BadgeDetailSheet';
import ChallengeGoalCard from '../src/pages/trials/ChallengeGoalCard';
import RareDropReveal from '../src/components/RareDropReveal';
import Companions from '../src/pages/bestiary/party/Companions';
import PetCeremonyModal from '../src/pages/bestiary/PetCeremonyModal';
import Inventory from '../src/pages/Inventory';
import Button from '../src/components/Button';

const params = new URLSearchParams(window.location.search);
applyTheme(params.get('theme') || 'hyrule');
localStorage.setItem('abby_auth_token', 'synthetic-browser-fixture-token');

// An in-memory, authored test glyph exercises image layout without licensed
// runtime art, an asset download or a real person's data.
const image = `data:image/svg+xml,${encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect x="4" y="4" width="56" height="56" rx="16" fill="#decaf5"/><text x="32" y="45" font-size="40" text-anchor="middle" fill="#634385">★</text></svg>')}`;
const sprites = { getSpriteMeta: (key) => key?.startsWith('fixture-') ? { url: image, frames: 1 } : null };
const badge = { id: 1, name: 'Fixture milestone', icon: '🏅', rarity: 'rare', xp_bonus: 50, coin_bonus: 35, criterion_type: 'projects_completed', criterion_value: 5, description: 'Recognizes steady progress on five projects.' };
const reward = { item_id: 8, item_name: 'Fixture progress frame', item_icon: '🖼️', item_sprite_key: 'fixture-frame', item_rarity: 'epic', item_effect_summary: 'An earned frame to choose for your profile.', quantity: 1 };
const goal = {
  id: 'goal:11', name: 'Fixture steady progress', origin: 'catalog', status: 'active',
  description: 'Complete everyday tasks to collect a named reward.', metric: 'count', progress: '2', target: '5', unit: 'activities',
  starts_at: '2026-10-12T07:00:00Z', ends_at: '2026-10-19T07:00:00Z',
  what_counts: 'Saved matching activities count automatically.',
  rewards: { coins: 20, xp: 30, items: [reward] }, reward_receipt: { status: 'pending' },
};

export default function Fixture() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const view = params.get('view') || 'goal';
  return <main className="mx-auto max-w-3xl space-y-4 p-4">
    <h1 className="font-body text-lede font-bold text-ink-primary">Reward rarity · synthetic example</h1>
    {view === 'badge' && <>
      <BadgeSigil badge={badge} earned={false} hint="Complete 5 projects" onSelect={() => setOpen(true)} />
      {open && <BadgeDetailSheet entry={{ badge, earned: false }} onClose={() => setOpen(false)} />}
    </>}
    {view === 'goal' && <ChallengeGoalCard goal={goal} onSelect={() => {}} />}
    {view === 'drop' && <>
      <Button onClick={() => setOpen(true)}>Show rare reward</Button>
      {open && <RareDropReveal drop={{ id: 8, item_name: reward.item_name, item_icon: reward.item_icon, item_sprite_key: reward.item_sprite_key, item_rarity: 'epic', item_type: 'cosmetic_frame', item_catalog_available: true, item_description: 'A frame earned through your progress.', item_effect_summary: reward.item_effect_summary }} onDismiss={() => setOpen(false)} />}
    </>}
    {view === 'food' && <AuthProvider><Companions /></AuthProvider>}
    {view === 'inventory' && <Inventory />}
    {view === 'expedition' && <>
      <Button onClick={() => setOpen(true)}>Show expedition rewards</Button>
      {open && <PetCeremonyModal mode="expedition_return" onDismiss={() => setOpen(false)} expedition={{
        coins_awarded: 75, tier: 'long', mount: { species_name: 'Fixture pet', species_sprite_key: 'fixture-pet', species_icon: '🐾', potion_slug: 'base' },
        items: [{ name: 'Fixture berries', sprite_key: 'fixture-food', icon: '🫐', rarity: 'rare', quantity: 2, effect_summary: 'Adds 10 growth, plus 10 more for a pet that prefers this food.' }, { name: 'Fixture frame', sprite_key: 'fixture-frame', icon: '🖼️', rarity: 'epic', quantity: 1, salvaged_to_coins: 25 }],
      }} />}
    </>}
    <output aria-label="Fixture location" className="block text-caption text-ink-secondary">{location.pathname}{location.search}{location.hash}</output>
  </main>;
}

createRoot(document.getElementById('root')).render(<MemoryRouter><SpriteCatalogContext.Provider value={sprites}><Fixture /></SpriteCatalogContext.Provider></MemoryRouter>);
