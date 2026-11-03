import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import { buildChallengeGoal } from '../../test/challenges';
import ChallengeGoalCard, { ChallengeGoalDetail } from './ChallengeGoalCard';
import { resolveCatalogIcon } from '../../catalog/sharedCatalogIcons';
import { resolvePedestalImage } from '../../pedestal/pedestalRelease';
import retainedDiscoveryPromises from '../../../../contracts/api/fixtures/challenge-discovery-retained-promises.json';

vi.mock('../../pedestal/pedestalRelease', () => ({ resolvePedestalImage: vi.fn() }));
vi.mock('../../catalog/sharedCatalogIcons', () => ({ resolveCatalogIcon: vi.fn() }));
beforeEach(() => { resolvePedestalImage.mockReturnValue(null); resolveCatalogIcon.mockReturnValue(null); });

describe('Challenge goal cards', () => {
  it.each([false, true])('keeps the actual earlier egg detail out of Today pinning while preserving its promise (pinned: %s)', (pinned) => {
    const goal = { ...retainedDiscoveryPromises.results[0], pinned };
    const onPin = vi.fn();
    renderWithProviders(<ChallengeGoalDetail goal={goal} onClose={() => {}} onPin={onPin} />, { withAuth: false });
    expect(screen.queryByRole('button', { name: /^(?:Pin to Today|Unpin)$/ })).toBeNull();
    expect(screen.getByText('Earlier egg rewards keep their saved progress. Your chosen discovery stays on Today.')).toBeInTheDocument();
    expect(screen.getByText('3 / 8 activities')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Completion reward items' })).toHaveTextContent('Mushroom Egg');
    expect(screen.getByRole('list', { name: 'Completion reward items' })).toHaveTextContent('Fire Potion');
    expect(onPin).not.toHaveBeenCalled();
  });

  it.each([false, true])('keeps ordinary detail pinning functional (pinned: %s)', async (pinned) => {
    const goal = buildChallengeGoal({ pinned });
    const onPin = vi.fn();
    const { user } = renderWithProviders(<ChallengeGoalDetail goal={goal} onClose={() => {}} onPin={onPin} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: pinned ? 'Unpin' : 'Pin to Today', exact: true }));
    expect(onPin).toHaveBeenCalledWith(goal);
    expect(screen.getByText(/Pinning only keeps this goal on Today/)).toBeInTheDocument();
  });

  it.each([false, true])('shows and opens a personal parent goal’s future schedule (paused: %s)', async (paused) => {
    const goal = buildChallengeGoal({ repeat_weekly: true, schedule: { next_week: { paused } } });
    const select = vi.fn();
    const { user } = renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={select} isPersonalParent />, { withAuth: false });
    expect(screen.getByText(paused ? 'Future weeks paused' : 'Future weeks scheduled')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Manage future weeks' }));
    expect(select).toHaveBeenCalledWith(goal);
  });

  it('keeps future schedule management and parent status copy out of a child goal card', () => {
    const goal = buildChallengeGoal({ repeat_weekly: true, schedule: { next_week: { paused: true } } });
    renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={() => {}} />, { withAuth: false });
    expect(screen.queryByRole('button', { name: 'Manage future weeks' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Future weeks (paused|scheduled)/)).not.toBeInTheDocument();
  });
  it.each(['card', 'detail'])('shows an untimed goal without inventing a deadline in its %s', (surface) => {
    const goal = buildChallengeGoal({ name: 'Reading Companion', origin: 'catalog', ends_at: null, repeat_weekly: false });
    renderWithProviders(surface === 'card'
      ? <ChallengeGoalCard goal={goal} onSelect={() => {}} />
      : <ChallengeGoalDetail goal={goal} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText('No deadline')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.queryByText(/Goal period|Counts work before|Period ended|Invalid Date|NaN/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add .* to calendar/i })).not.toBeInTheDocument();
  });

  it.each(['card', 'detail'])('explains an unavailable retry reward and disables the action in the %s', async (surface) => {
    const goal = buildChallengeGoal({ status: 'expired', origin: 'catalog', retry: { allowed: false, reason: 'reward_unavailable' } });
    const onRetry = vi.fn();
    const { user } = renderWithProviders(surface === 'card'
      ? <ChallengeGoalCard goal={goal} onSelect={() => {}} onRetry={onRetry} />
      : <ChallengeGoalDetail goal={goal} onClose={() => {}} onRetry={onRetry} />, { withAuth: false });
    expect(screen.getByText("A new attempt can't start while this challenge's reward is unavailable.")).toBeInTheDocument();
    const retry = screen.getByRole('button', { name: `Try ${goal.name} again` });
    expect(retry).toBeDisabled();
    await user.click(retry);
    expect(onRetry).not.toHaveBeenCalled();
  });

  it.each(['card', 'detail'])('explains a closed retry without presenting its original reward as pending or paid in the %s', (surface) => {
    const goal = buildChallengeGoal({ status: 'closed', origin: 'catalog', closed_reason: 'reward_already_awarded', retry: { allowed: false, reason: 'closed' }, reward_receipt: { status: 'pending', coins_awarded: 0, xp_awarded: 0 } });
    renderWithProviders(surface === 'card' ? <ChallengeGoalCard goal={goal} onSelect={() => {}} /> : <ChallengeGoalDetail goal={goal} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText('Attempt closed')).toBeInTheDocument();
    expect(screen.getByText("Another attempt earned this challenge's one-time bonus.")).toBeInTheDocument();
    expect(screen.getByText('Original completion bonus · 10 coins')).toBeInTheDocument();
    expect(screen.queryByText(/Bonus pending|Bonus earned automatically/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /try .* again/i })).not.toBeInTheDocument();
  });

  it('shows the exact exclusive deadline of a rolling period in its saved timezone', () => {
    const goal = buildChallengeGoal({ timezone: 'America/New_York', starts_at: '2026-10-28T16:15:00Z', ends_at: '2026-11-04T17:15:00Z' });
    renderWithProviders(<ChallengeGoalDetail goal={goal} timezone="Pacific/Auckland" onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText(/Goal period/)).toHaveTextContent('Goal period Oct 28, 2026 – Nov 4, 2026');
    const deadline = screen.getByText(/Counts work before/);
    expect(deadline).toHaveTextContent('Nov 4, 2026');
    expect(deadline).toHaveTextContent('12:15 PM EST');
    expect(deadline.querySelector('time')).toHaveAttribute('dateTime', goal.ends_at);
    expect(screen.queryByText(/Completion recorded/)).not.toBeInTheDocument();
  });

  it('keeps an incomplete ended period truthful without a completion timestamp', () => {
    const goal = buildChallengeGoal({ status: 'expired', progress: '1', completed_at: null, updated_at: '2026-10-20T01:00:00Z' });
    renderWithProviders(<ChallengeGoalCard goal={goal} timezone="America/Phoenix" onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText('Period ended')).toBeInTheDocument();
    expect(screen.getByText(/Goal period/)).toHaveTextContent('2026');
    expect(screen.getByText('1 / 2 miles')).toBeInTheDocument();
    expect(screen.queryByText(/Completion recorded|Completion date unavailable/)).not.toBeInTheDocument();
  });

  it.each(['card', 'detail'])('keeps the saved period beside a later recorded completion in the %s', (surface) => {
    const goal = buildChallengeGoal({
      status: 'completed', timezone: 'America/Phoenix',
      completed_at: '2026-10-20T01:00:00Z',
    });
    renderWithProviders(surface === 'card'
      ? <ChallengeGoalCard goal={goal} timezone="UTC" onSelect={() => {}} />
      : <ChallengeGoalDetail goal={goal} timezone="UTC" onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText(/Goal period/)).toHaveTextContent('Goal period Oct 12, 2026 – Oct 18, 2026');
    expect(screen.getByText(/Completion recorded/)).toHaveTextContent('Completion recorded Oct 19, 2026');
    expect(screen.queryByText(/^(late|early|on time)\b/i)).not.toBeInTheDocument();
  });

  it.each(['active', 'expired'])('shows the automatic goal period in %s cards, including background bonuses', (status) => {
    const goal = buildChallengeGoal({ status, origin: 'catalog', timezone: 'America/Phoenix' });
    renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText(/Goal period/)).toHaveTextContent('Goal period Oct 12, 2026 – Oct 18, 2026');
    expect(screen.queryByText(/Completion recorded/)).not.toBeInTheDocument();
  });

  it('leaves a legacy completion date unknown instead of using its updated timestamp', () => {
    const goal = buildChallengeGoal({
      legacy: true, status: 'completed', completed_at: null, updated_at: '2026-10-21T01:00:00Z',
    });
    renderWithProviders(<ChallengeGoalDetail goal={goal} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText('Completion date unavailable')).toBeInTheDocument();
    expect(screen.queryByText(/Completion recorded/)).not.toBeInTheDocument();
  });

  it('retains exact catalog artwork, long title and pin control within the child card', async () => {
    resolveCatalogIcon.mockImplementation((id) => id === 'item-meat' ? { url: '/synthetic/meat.png' } : null);
    const goal = buildChallengeGoal({ name: 'An extraordinarily long challenge name to keep fully readable', catalog_icon: 'item-meat' });
    const onPin = vi.fn();
    const { user } = renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={() => {}} onPin={onPin} />, { withAuth: false });
    expect(screen.getByRole('img', { name: goal.name })).toHaveAttribute('src', '/synthetic/meat.png');
    expect(screen.getByRole('heading', { name: goal.name })).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0.75');
    await user.click(screen.getByRole('button', { name: 'Pin to Today' }));
    expect(onPin).toHaveBeenCalledWith(goal);
  });

  it.each(['card', 'detail'])('identifies the promised reward rarity in the %s without implying delivery', (surface) => {
    const goal = buildChallengeGoal({ rewards: { coins: 10, xp: 20, items: [{ item_name: 'Canvas frame', item_rarity: 'epic', item_icon: '🖼️', quantity: 1 }] } });
    renderWithProviders(surface === 'card' ? <ChallengeGoalCard goal={goal} onSelect={() => {}} /> : <ChallengeGoalDetail goal={goal} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText('epic')).toBeInTheDocument();
    expect(screen.getByText('Canvas frame ×1')).toBeInTheDocument();
    expect(screen.getByText('Completion bonus · 10 coins · 20 XP')).toBeInTheDocument();
    expect(screen.queryByText(/earned automatically/i)).toBeNull();
  });

  it.each([false, true])('uses the tall kit without changing the saved reward or parent role (parent: %s)', (isParent) => {
    const goal = buildChallengeGoal({ rewards: { coins: 10, xp: 20, items: [] } });
    const { container } = renderWithProviders(<ChallengeGoalCard goal={goal} isParent={isParent} onSelect={() => {}} />, { withAuth: false });
    expect(container.querySelector('[data-achievement-card="tall"]')).toBeInTheDocument();
    expect(container.querySelector('[data-pedestal-image="card-front-light"]')).toBeNull();
    expect(screen.getByRole('article', { name: goal.name })).toBeInTheDocument();
    expect(screen.getByText('Completion bonus · 10 coins · 20 XP')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `View ${goal.name}` })).toBeEnabled();
  });

  it('opens the full goal rather than an inert whole-card target', async () => {
    const select = vi.fn();
    const goal = buildChallengeGoal();
    const { user } = renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={select} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: `View ${goal.name}` }));
    expect(select).toHaveBeenCalledWith(goal);
  });

  it('shows the exact settled bonus instead of the planned reward when boosted', () => {
    renderWithProviders(<ChallengeGoalCard goal={buildChallengeGoal({ status: 'completed', reward_receipt: { status: 'awarded', coins_awarded: 20, xp_awarded: 40 } })} onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText('Bonus earned automatically · 20 coins · 40 XP')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pin/i })).not.toBeInTheDocument();
  });

  it.each(['card', 'detail'])('does not report an undelivered preview egg as earned in the %s', (surface) => {
    const goal = buildChallengeGoal({
      status: 'completed', rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: { status: 'awarded', coins_awarded: 20, xp_awarded: 40, items: [] },
    });
    renderWithProviders(surface === 'card'
      ? <ChallengeGoalCard goal={goal} onSelect={() => {}} />
      : <ChallengeGoalDetail goal={goal} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText('Bonus earned automatically · 20 coins · 40 XP')).toBeInTheDocument();
    expect(screen.queryByText(/Egg/)).not.toBeInTheDocument();
  });

  it.each(['card', 'detail'])('shows the actual delivered item and quantity instead of the frozen preview in the %s', (surface) => {
    const goal = buildChallengeGoal({
      status: 'completed', rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: { status: 'awarded', coins_awarded: 10, xp_awarded: 20, items: [{ item_name: 'Canvas frame', quantity: 2 }] },
    });
    renderWithProviders(surface === 'card'
      ? <ChallengeGoalCard goal={goal} onSelect={() => {}} />
      : <ChallengeGoalDetail goal={goal} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText('Bonus earned automatically · 10 coins · 20 XP')).toBeInTheDocument();
    expect(screen.getByText('Canvas frame ×2')).toBeInTheDocument();
    expect(screen.queryByText(/Egg/)).not.toBeInTheDocument();
  });

  it('does not fall back to the preview when an awarded receipt has no saved item details', () => {
    const goal = buildChallengeGoal({
      status: 'completed', rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: { status: 'awarded', coins_awarded: 10, xp_awarded: 20 },
    });
    renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText('Bonus earned automatically · 10 coins · 20 XP')).toBeInTheDocument();
    expect(screen.queryByText(/Egg/)).not.toBeInTheDocument();
  });

  it.each([0, 12])('does not describe a salvaged egg as delivered or add its %s Coins twice', (salvage) => {
    const goal = buildChallengeGoal({
      status: 'completed', rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: {
        status: 'awarded', coins_awarded: 10 + salvage, xp_awarded: 20,
        items: [{ item_name: 'Egg', quantity: 1, salvaged_to_coins: salvage }],
      },
    });
    renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText(`Bonus earned automatically · ${10 + salvage} coins · 20 XP`)).toBeInTheDocument();
    expect(screen.queryByText(/Egg/)).not.toBeInTheDocument();
  });

  it('does not infer delivered items for a completed legacy goal without an award receipt', () => {
    const goal = buildChallengeGoal({
      legacy: true, status: 'completed', rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: { status: 'legacy', coins_awarded: 0, xp_awarded: 0 },
    });
    renderWithProviders(<ChallengeGoalDetail goal={goal} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByText('Original completion bonus · 10 coins · 20 XP')).toBeInTheDocument();
    expect(screen.queryByText(/Egg/)).not.toBeInTheDocument();
  });

  it.each(['active', 'completed'])('keeps the promised item preview while an %s goal has no paid receipt', (status) => {
    const goal = buildChallengeGoal({
      status, rewards: { coins: 10, xp: 20, items: [{ item_name: 'Egg', quantity: 1 }] },
      reward_receipt: { status: 'pending', coins_awarded: 0, xp_awarded: 0 },
    });
    renderWithProviders(<ChallengeGoalCard goal={goal} onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText(`${status === 'active' ? 'Completion bonus' : 'Bonus pending'} · 10 coins · 20 XP`)).toBeInTheDocument();
    expect(screen.getByText('Egg ×1')).toBeInTheDocument();
    expect(screen.queryByText(/Bonus earned automatically/)).not.toBeInTheDocument();
  });

  it('retains ended legacy attempts in history without treating them as active', () => {
    renderWithProviders(<ChallengeGoalCard goal={buildChallengeGoal({ legacy: true, status: 'failed' })} onSelect={() => {}} />, { withAuth: false });
    expect(screen.getByText('Period ended')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pin/i })).not.toBeInTheDocument();
  });

  it('keeps a parent viewing a child goal from opening the child logging form', () => {
    renderWithProviders(<ChallengeGoalDetail goal={buildChallengeGoal()} canAct={false} onClose={() => {}} />, { withAuth: false });
    expect(screen.getByRole('heading', { name: 'What counts' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Log a run' })).not.toBeInTheDocument();
  });
});
