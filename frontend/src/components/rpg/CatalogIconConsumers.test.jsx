import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { buildChallengeGoal } from '../../test/challenges';
import { emptyPulse } from '../../test/pulseFixtures';
import CatalogCard from '../../pages/manage/CatalogCard';
import CodexSection from '../../pages/manage/CodexSection';
import MountsBlock from '../../pages/manage/MountsBlock';
import Inventory from '../../pages/Inventory';
import ChildDashboard from '../../pages/ChildDashboard';
import Companions from '../../pages/bestiary/party/Companions';
import CosmeticSigil from '../../pages/character/CosmeticSigil';
import SavedCosmetics from '../../pages/character/SavedCosmetics';
import QuestTile from '../../pages/trials/QuestTile';
import ActiveQuestFolio from '../../pages/trials/ActiveQuestFolio';
import ChallengeGoalCard, { ChallengeGoalDetail } from '../../pages/trials/ChallengeGoalCard';
import PinnedChallengeCard from '../dashboard/PinnedChallengeCard';
import RewardCard from '../../pages/rewards/RewardCard';
import DropToastStack from '../DropToastStack';
import RareDropReveal from '../RareDropReveal';

// Exercise the API-to-component binding independently from manifest loading.
// CatalogIcon's own tests cover real image loading and fallback recovery.
vi.mock('./CatalogIcon', () => ({
  default: ({ assetId, spriteKey, fallbackSpriteKey, alt }) => <span
    data-testid="catalog-icon"
    data-asset-id={assetId || ''}
    data-sprite-key={spriteKey || ''}
    data-fallback-key={fallbackSpriteKey || ''}
    aria-label={alt}
  />,
}));

vi.mock('framer-motion', async () => ({
  ...await vi.importActual('framer-motion'),
  AnimatePresence: ({ children }) => children,
}));

const item = {
  id: 1, name: 'Small coin pouch', item_type: 'coin_pouch', rarity: 'common',
  icon: '👛', sprite_key: 'money-purse', catalog_icon: 'item-small-coin-pouch',
};
const definition = {
  id: 2, name: 'Daily focus', icon: '🎯', sprite_key: 'legacy-challenge',
  catalog_icon: 'challenge-daily-focus', quest_type: 'collection',
  target_value: 3, duration_days: 7, coin_reward: 10,
  reward_items: [{ id: 3, item_name: item.name, item_icon: item.icon,
    item_sprite_key: item.sprite_key, item_catalog_icon: item.catalog_icon, quantity: 1 }],
};

function expectIcons(...ids) {
  expect(screen.getAllByTestId('catalog-icon').map((node) => node.dataset.assetId)).toEqual(ids);
}

beforeEach(() => {
  window.localStorage.removeItem('manage:codex:active-section');
});

describe('Catalog image consumer bindings', () => {
  it('retains a catalog card sprite fallback alongside the explicit content identity', () => {
    renderWithProviders(<CatalogCard name="Bird" assetId="portrait-bird" spriteKey="cute-chick-mount" fallbackSpriteKey="cute-chick" />);
    expectIcons('portrait-bird');
    expect(screen.getByTestId('catalog-icon')).toHaveAttribute('data-fallback-key', 'cute-chick');
  });

  it('uses separate identities for items sharing one legacy sprite in inventory', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json([
      { id: 1, quantity: 1, item },
      { id: 2, quantity: 1, item: { ...item, id: 2, name: 'Large coin pouch', catalog_icon: 'item-large-coin-pouch' } },
    ])));
    renderWithProviders(<Inventory />, { withAuth: false });
    await screen.findByText('Small coin pouch');
    expectIcons('item-small-coin-pouch', 'item-large-coin-pouch');
    expect(screen.getAllByTestId('catalog-icon').map((node) => node.dataset.spriteKey)).toEqual(['money-purse', 'money-purse']);
  });

  it('uses the flattened item identity in the Today recent-items grid', async () => {
    server.use(http.get('*/api/drops/recent/', () => HttpResponse.json([
      { id: 50, item_name: item.name, item_sprite_key: item.sprite_key, item_catalog_icon: item.catalog_icon, item_rarity: 'common' },
    ])));
    renderWithProviders(<ChildDashboard data={{ next_actions: [] }} />);
    await screen.findByRole('button', { name: `${item.name} — open inventory` });
    expectIcons(item.catalog_icon);
  });

  it('uses the owned food identity in the companion feed picker', async () => {
    const pet = { id: 1, species: { name: 'Chick', sprite_key: 'cute-chick', slug: 'chick' }, potion: { name: 'Base', slug: 'base' }, is_active: true, growth_points: 10 };
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [pet], mounts: [], total_possible: 1 })),
      http.get('*/api/inventory/', () => HttpResponse.json([{ quantity: 2, item: { ...item, name: 'Berries', item_type: 'food', catalog_icon: 'item-berries' } }])),
    );
    const { user } = renderWithProviders(<Companions />, { withAuth: false });
    await user.click(await screen.findByRole('button', { name: 'Feed your companion' }));
    expectIcons('item-berries');
  });

  it('binds catalog item thumbnails and their detail sheet to the server identity', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([item])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    const { user } = renderWithProviders(<CodexSection />, { withAuth: false });
    await screen.findByText(item.name);
    expectIcons(item.catalog_icon);
    await user.click(screen.getByRole('button', { name: new RegExp(item.name, 'i') }));
    expectIcons(item.catalog_icon, item.catalog_icon);
  });

  it('binds catalog challenge and reward previews to their own identities', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([definition])),
    );
    const { user } = renderWithProviders(<CodexSection />, { withAuth: false });
    await user.click(await screen.findByRole('tab', { name: /Challenges/ }));
    expectIcons(definition.catalog_icon);
    await user.click(screen.getByRole('button', { name: new RegExp(definition.name, 'i') }));
    expectIcons(definition.catalog_icon, definition.catalog_icon, item.catalog_icon);
  });

  it('uses only the grown catalog portrait identity in a grown-species card', () => {
    renderWithProviders(<MountsBlock species={[{ id: 1, name: 'Chick', sprite_key: 'cute-chick', catalog_icon: 'portrait-chick', grown_catalog_icon: 'portrait-bird' }]} />);
    expectIcons('portrait-bird');
    expect(screen.getByTestId('catalog-icon')).toHaveAttribute('data-sprite-key', 'cute-chick-mount');
  });

  it('keeps cosmetic ownership and equip handling with the catalog preview', async () => {
    const onEquip = vi.fn();
    const title = { id: 80, name: 'Master Crafter', item_type: 'cosmetic_title', rarity: 'rare', catalog_icon: 'title-master-crafter' };
    const { user } = renderWithProviders(<CosmeticSigil entry={{ item: title, owned: true, equipped: false }} slot="active_title" onEquip={onEquip} />);
    expectIcons(title.catalog_icon);
    await user.click(screen.getByRole('button'));
    expect(onEquip).toHaveBeenCalledWith(title.id);
  });

  it('previews the worn frame and retains its owned equip action', async () => {
    const frame = { id: 81, slug: 'frame-laurel', name: 'Laurel Wreath Frame', item_type: 'cosmetic_frame', rarity: 'legendary' };
    const onEquip = vi.fn();
    const { user, container } = renderWithProviders(<CosmeticSigil entry={{ item: frame, owned: true, equipped: false }}
      slot="active_frame" previewName="Abby" onEquip={onEquip} />);
    expect(container.querySelector('[data-portrait-frame="laurel"]')).not.toBeNull();
    await user.click(screen.getByRole('button', { name: /Laurel Wreath Frame.*click to equip/ }));
    expect(onEquip).toHaveBeenCalledWith(frame.id);
  });

  it('keeps earlier cosmetic removal alongside its catalog image', async () => {
    const saved = { ...item, catalog_available: false };
    const onRemove = vi.fn();
    const { user } = renderWithProviders(<SavedCosmetics cosmetics={{ active_frame: [saved] }} profile={{ active_frame: saved }} onRemove={onRemove} />);
    expectIcons(item.catalog_icon);
    await user.click(screen.getByRole('button', { name: 'Remove previous selection' }));
    expect(onRemove).toHaveBeenCalledWith('active_frame');
  });

  it('binds the available challenge tile to its catalog definition', () => {
    renderWithProviders(<QuestTile quest={definition} chapter="available" />);
    expectIcons(definition.catalog_icon);
  });

  it('binds saved challenge thumbnails and reward item previews', () => {
    renderWithProviders(<ActiveQuestFolio quest={{ id: 8, status: 'active', current_progress: 1, progress_percent: 33, definition }} />);
    expectIcons(definition.catalog_icon, item.catalog_icon);
  });

  it.each(['card', 'detail', 'pinned'])('shows the authoritative automatic challenge icon in the %s', (surface) => {
    const goal = buildChallengeGoal({ origin: 'catalog', catalog_icon: definition.catalog_icon });
    renderWithProviders(surface === 'card' ? <ChallengeGoalCard goal={goal} />
      : surface === 'detail' ? <ChallengeGoalDetail goal={goal} onClose={() => {}} />
        : <PinnedChallengeCard goal={goal} />, { withAuth: false });
    expectIcons(definition.catalog_icon);
  });

  it.each(['card', 'detail', 'pinned'])('keeps parent-authored custom goals free of invented catalog icons in the %s', (surface) => {
    const goal = buildChallengeGoal({ origin: 'parent', catalog_icon: null });
    renderWithProviders(surface === 'card' ? <ChallengeGoalCard goal={goal} />
      : surface === 'detail' ? <ChallengeGoalDetail goal={goal} onClose={() => {}} />
        : <PinnedChallengeCard goal={goal} />, { withAuth: false });
    expect(screen.queryByTestId('catalog-icon')).not.toBeInTheDocument();
  });

  it.each(['digital_item', 'both'])('binds a %s shop reward to its nested item identity', (fulfillmentKind) => {
    renderWithProviders(<RewardCard reward={{ id: 3, name: 'Pouch offer', fulfillment_kind: fulfillmentKind, item_definition_detail: item }} />);
    expectIcons(item.catalog_icon);
  });

  it('preserves the parent-selected real-world reward icon even when an item detail is present', () => {
    renderWithProviders(<RewardCard reward={{ id: 3, name: 'Picnic', icon: '🧺', fulfillment_kind: 'real_world', item_definition_detail: item }} />);
    expect(screen.queryByTestId('catalog-icon')).not.toBeInTheDocument();
    expect(screen.getByText('🧺')).toBeInTheDocument();
  });

  it('uses the flattened item identity on new common drop toasts', async () => {
    const { beat } = renderWithProviders(<DropToastStack />, { withAuth: false, pulse: emptyPulse() });
    beat(emptyPulse({ recent_drops: [{ id: 51, item_name: item.name, item_sprite_key: item.sprite_key, item_catalog_icon: item.catalog_icon, item_rarity: 'common' }] }));
    await waitFor(() => expectIcons(item.catalog_icon));
  });

  it('uses the same flattened identity on rare reveals', () => {
    renderWithProviders(<RareDropReveal drop={{ id: 52, item_name: item.name, item_sprite_key: item.sprite_key, item_catalog_icon: item.catalog_icon, item_rarity: 'rare' }} />);
    expectIcons(item.catalog_icon);
  });
});
