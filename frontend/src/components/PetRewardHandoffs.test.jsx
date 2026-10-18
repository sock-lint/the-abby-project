import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { useLocation } from 'react-router-dom';
import { renderWithProviders, screen } from '../test/render';
import { emptyPulse } from '../test/pulseFixtures';
import { buildChallengeGoal } from '../test/challenges';
import { buildUser } from '../test/factories';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import DropToastStack from './DropToastStack';
import QuestProgressToastStack from './QuestProgressToastStack';
import ChallengeGoalCard, { ChallengeGoalDetail } from '../pages/trials/ChallengeGoalCard';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

beforeEach(() => { server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser()))); });

function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current page">{location.pathname}{location.search}</output>;
}

function watchMutations() {
  const writes = spyHandler('post', /\/api\/(?:pets|mounts|challenges|inventory)\//, {});
  server.use(writes.handler);
  return writes.calls;
}

const petItem = (item_type, overrides = {}) => ({
  item_id: { egg: 101, potion: 102, food: 103 }[item_type], item_name: `${item_type} reward`, item_type, quantity: 1,
  ...overrides,
});

function completedGoal(items, overrides = {}) {
  return buildChallengeGoal({
    status: 'completed',
    reward_receipt: { status: 'awarded', coins_awarded: 5, xp_awarded: 10, items },
    ...overrides,
  });
}

describe('Earned pet item handoffs', () => {
  it.each([
    ['egg', 'common', true, 'Go to Hatchery', '/bestiary?tab=hatchery'],
    ['potion', 'common', true, 'Go to Hatchery', '/bestiary?tab=hatchery'],
    ['food', 'uncommon', true, 'Feed a companion', '/bestiary?tab=companions'],
    ['food', 'common', false, 'Feed a companion', '/bestiary?tab=companions'],
  ])('opens existing controls for an earned %s drop without consuming it (rarity: %s)', async (type, rarity, available, label, destination) => {
    const writes = watchMutations();
    const { user, beat } = renderWithProviders(<><DropToastStack /><LocationProbe /></>, {
      withAuth: false, route: '/quests', pulse: emptyPulse(),
    });
    beat(emptyPulse({ recent_drops: [{
      id: 1, ...petItem(type), item_rarity: rarity, item_catalog_available: available,
      was_salvaged: false,
    }] }));
    const link = await screen.findByRole('link', { name: label });
    expect(link).toHaveAttribute('href', destination);
    await user.tab();
    expect(link).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('status', { name: 'Current page' })).toHaveTextContent(destination);
    expect(screen.queryByText(`You got: ${type} reward`)).not.toBeInTheDocument();
    expect(writes).toEqual([]);
  });

  it.each([
    { item_type: 'egg', was_salvaged: true },
    { item_type: 'potion', item_catalog_available: false },
    { item_type: undefined },
  ])('keeps a salvaged, unavailable or old untyped drop informational: %j', async (overrides) => {
    const writes = watchMutations();
    const { beat } = renderWithProviders(<DropToastStack />, { withAuth: false, pulse: emptyPulse() });
    beat(emptyPulse({ recent_drops: [{ id: 2, item_name: 'Earlier reward', item_rarity: 'common', ...overrides }] }));
    await screen.findByText(/Earlier reward/);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(writes).toEqual([]);
  });

  it.each(['card', 'detail'])('opens care or hatching from actual awarded items in the challenge %s', async (surface) => {
    const writes = watchMutations();
    const close = vi.fn();
    const goal = completedGoal([petItem('egg'), petItem('potion'), petItem('food')]);
    const { user } = renderWithProviders(<>
      {surface === 'card' ? <ChallengeGoalCard goal={goal} onSelect={() => {}} />
        : <ChallengeGoalDetail goal={goal} onClose={close} />}
      <LocationProbe />
    </>, { withAuth: false, route: '/quests?tab=trials' });
    expect(screen.getByText('egg reward ×1')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Go to Hatchery' })).toHaveLength(1);
    const destination = surface === 'card' ? '/bestiary?tab=companions' : '/bestiary?tab=hatchery';
    await user.click(screen.getByRole('link', { name: surface === 'card' ? 'Feed a companion' : 'Go to Hatchery' }));
    expect(screen.getByRole('status', { name: 'Current page' })).toHaveTextContent(destination);
    if (surface === 'detail') expect(close).toHaveBeenCalledTimes(1);
    expect(writes).toEqual([]);
  });

  it.each([
    { status: 'active', rewards: { coins: 5, xp: 10, items: [petItem('egg')] }, reward_receipt: { status: 'pending' } },
    { status: 'completed', rewards: { coins: 5, xp: 10, items: [petItem('egg')] }, reward_receipt: { status: 'pending' } },
    { status: 'completed', legacy: true, reward_receipt: { status: 'legacy' } },
    { reward_receipt: { status: 'awarded', items: [petItem('egg', { salvaged_to_coins: 0 })] } },
    { reward_receipt: { status: 'awarded', items: [petItem('egg', { item_catalog_available: false })] } },
    { reward_receipt: { status: 'awarded', items: [{ item_id: 101, item_name: 'Earlier egg', quantity: 1 }] } },
  ])('does not offer owned-item actions for previews, converted or unsupported receipts: %j', (overrides) => {
    const goal = completedGoal([], overrides);
    renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={() => {}} />, { withAuth: false });
    expect(screen.queryByRole('link', { name: /Hatchery|Feed a companion/ })).not.toBeInTheDocument();
    if (overrides.reward_receipt.items?.[0]?.item_name === 'Earlier egg') {
      expect(screen.getByText('Earlier egg ×1')).toBeInTheDocument();
    }
  });

  it.each(['card', 'detail'])('does not send a parent viewing a child’s %s receipt to their own pets', (surface) => {
    const goal = completedGoal([petItem('egg'), petItem('food')]);
    renderWithProviders(surface === 'card'
      ? <ChallengeGoalCard goal={goal} isParent onSelect={() => {}} />
      : <ChallengeGoalDetail goal={goal} canAct={false} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText('egg reward ×1')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Hatchery|Feed a companion/ })).not.toBeInTheDocument();
  });

  it('links actual item awards in a bounded activity receipt even when their goal is outside its summary', async () => {
    const writes = watchMutations();
    const { user } = renderWithProviders(<><QuestProgressToastStack /><LocationProbe /></>, {
      route: '/quests', pulse: emptyPulse({ challenge_receipts: [{
        id: 'activity:handoff', daily_bonus: null,
        goals: Array.from({ length: 4 }, (_, index) => ({
          id: `goal:${index}`, name: `Trail ${index}`, completed: true, progress: '1', target: '1', unit: 'actions',
          rewards: { coins: 5, xp: 10, items: index === 3 ? [petItem('egg'), petItem('food')] : [] },
        })),
      }] }),
    });
    const link = await screen.findByRole('link', { name: 'Go to Hatchery' });
    expect(screen.queryByText('Trail 3')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Feed a companion' })).toHaveAttribute('href', '/bestiary?tab=companions');
    await user.click(link);
    expect(screen.getByRole('status', { name: 'Current page' })).toHaveTextContent('/bestiary?tab=hatchery');
    expect(screen.queryByText('Challenge progress')).not.toBeInTheDocument();
    expect(writes).toEqual([]);
  });

  it('never treats uncompleted goals, converted eggs or old item details as usable pet awards', async () => {
    renderWithProviders(<QuestProgressToastStack />, { pulse: emptyPulse({ challenge_receipts: [{
      id: 'activity:informational', daily_bonus: null,
      goals: [
        { id: 'goal:1', name: 'Still growing', completed: false, progress: '1', target: '2', unit: 'actions', rewards: { coins: 0, xp: 0, items: [petItem('egg')] } },
        { id: 'goal:2', name: 'Converted reward', completed: true, rewards: { coins: 5, xp: 10, items: [petItem('egg', { salvaged_to_coins: 0 })] } },
        { id: 'goal:3', name: 'Old reward', completed: true, rewards: { coins: 5, xp: 10, items: [{ item_name: 'Earlier egg', quantity: 1 }] } },
      ],
    }] }) });
    await screen.findByText('Challenge progress');
    expect(screen.queryByRole('link', { name: /Hatchery|Feed a companion/ })).not.toBeInTheDocument();
  });

});
