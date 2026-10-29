import { describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { renderWithProviders, screen, within } from '../../test/render';
import { buildChallengeGoal } from '../../test/challenges';
import ChallengesFolio from './ChallengesFolio';
import { selectDropdown } from '../../test/selectDropdown';
import retainedDiscoveryPromises from '../../../../contracts/api/fixtures/challenge-discovery-retained-promises.json';

describe('Challenges Task folio', () => {
  it('groups the actual accepted egg response behind a closed disclosure and preserves its saved target and supplies', async () => {
    const goal = retainedDiscoveryPromises.results[0];
    const select = vi.fn(), pin = vi.fn();
    const { user } = renderWithProviders(<ChallengesFolio goals={retainedDiscoveryPromises.results} pinnedGoal={goal} lockedCatalog={retainedDiscoveryPromises.locked_catalog} onSelect={select} onPin={pin} />, { withAuth: false });
    const disclosure = screen.getByText('Earlier egg rewards · 1').closest('details');
    expect(disclosure).not.toHaveAttribute('open');
    expect(screen.queryByRole('article', { name: goal.name })).toBeNull();
    expect(screen.queryByRole('region', { name: 'Pinned challenge' })).toBeNull();
    await user.click(screen.getByText('Earlier egg rewards · 1'));
    const saved = screen.getByRole('article', { name: goal.name });
    expect(saved).toHaveTextContent('3 / 8 activities');
    expect(within(saved).getByRole('list', { name: 'Completion reward items' })).toHaveTextContent('Mushroom Egg');
    expect(within(saved).getByRole('list', { name: 'Completion reward items' })).toHaveTextContent('Fire Potion');
    expect(within(saved).queryByRole('button', { name: /pin/i })).toBeNull();
    await user.click(within(saved).getByRole('button', { name: `View ${goal.name}` }));
    expect(select).toHaveBeenCalledWith(goal);
    expect(pin).not.toHaveBeenCalled();
  });

  it('keeps earlier egg promises in a closed group while parent goals and unrelated bonuses remain visible', async () => {
    const earlier = buildChallengeGoal({ id: 'goal:egg', origin: 'catalog', name: 'Saved Wolf Trail', progress: '9', target: '10', pinned: true, legacy_egg_promise: true });
    const parent = buildChallengeGoal({ id: 'goal:parent', name: 'Run together' });
    const bonus = buildChallengeGoal({ id: 'goal:bonus', origin: 'catalog', name: 'Read for fun', progress: '2' });
    const select = vi.fn(), pin = vi.fn();
    const { user } = renderWithProviders(<ChallengesFolio goals={[earlier, parent, bonus]} pinnedGoal={earlier} onSelect={select} onPin={pin} />, { withAuth: false });
    expect(screen.queryByRole('region', { name: 'Pinned challenge' })).toBeNull();
    expect(screen.queryByRole('article', { name: earlier.name })).toBeNull();
    expect(screen.getByRole('article', { name: parent.name })).toBeInTheDocument();
    expect(screen.getByRole('article', { name: bonus.name })).toBeInTheDocument();
    await user.click(screen.getByText('Earlier egg rewards · 1'));
    const saved = screen.getByRole('article', { name: earlier.name });
    expect(saved).toHaveTextContent('9 / 10 miles');
    expect(within(saved).queryByRole('button', { name: /pin/i })).toBeNull();
    await user.click(within(saved).getByRole('button', { name: `View ${earlier.name}` }));
    expect(select).toHaveBeenCalledWith(earlier);
    expect(pin).not.toHaveBeenCalled();
  });

  it('keeps all ended history accessible after retrying the last eligible attempt', async () => {
    const expired = buildChallengeGoal({ name: 'Ended bonus', origin: 'catalog', status: 'expired', retry: { allowed: true } });
    const fresh = buildChallengeGoal({ id: 'goal:fresh', name: 'Fresh bonus', origin: 'catalog', progress: '0', retry: { allowed: false } });
    function SavedAttempts() {
      const [goals, setGoals] = useState([expired]);
      return <ChallengesFolio goals={goals} onSelect={vi.fn()} onRetry={() => setGoals([
        { ...expired, retry: { allowed: false, latest_attempt_id: fresh.id } }, fresh,
      ])} />;
    }
    const { user } = renderWithProviders(<SavedAttempts />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Find challenges to try again' }));
    await user.click(screen.getByRole('button', { name: 'Try Ended bonus again' }));
    const filter = screen.getByRole('combobox', { name: 'Show history' });
    expect(filter).toHaveValue('retryable');
    expect(screen.getByText('No challenges can be tried again right now.')).toBeInTheDocument();
    await selectDropdown(user, filter, 'all');
    expect(screen.getByRole('article', { name: 'Ended bonus' })).toBeInTheDocument();
    expect(screen.getByText('History · 1')).toBeInTheDocument();
  });

  it('searches and filters the full bonus catalog without duplicating preview cards or hiding parent goals', async () => {
    const bonuses = Array.from({ length: 7 }, (_, index) => buildChallengeGoal({
      id: `goal:bonus-${index}`, origin: 'catalog', name: `Story ${index}`, progress: '0',
      metric: 'count', target: '5', unit: 'actions',
      catalog_repeatable: false, first_details_opened_at: null,
      qualifying_triggers: [index < 4 ? 'habit_log' : 'chore_complete'],
      what_counts: index < 4 ? 'positive habit taps' : 'approved chores',
      ends_at: `2026-10-${20 + index}T07:00:00Z`, timezone: 'America/Phoenix',
    }));
    const parent = buildChallengeGoal({ id: 'goal:parent', name: 'Parent running goal' });
    const { user } = renderWithProviders(<ChallengesFolio goals={[parent, ...bonuses]} onSelect={vi.fn()} />, { withAuth: false });
    await user.click(screen.getByText('Browse bonus challenges'));
    expect(screen.getAllByRole('article')).toHaveLength(8);
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Qualifying activity' }), 'chore_complete');
    expect(screen.getByText('3 of 7 bonus challenges')).toHaveAttribute('role', 'status');
    await user.type(screen.getByRole('searchbox', { name: 'Search bonus challenges' }), 'Story 6');
    expect(screen.getByText('1 of 7 bonus challenges')).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'Story 6' })).toHaveTextContent('5 activities · approved chores');
    expect(screen.getByRole('article', { name: 'Parent running goal' })).toBeInTheDocument();
    await user.type(screen.getByLabelText('Ends on or before'), '2026-10-23');
    expect(screen.getByText('No bonus challenges match these filters.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(screen.getByText('7 of 7 bonus challenges')).toBeInTheDocument();
    expect(screen.getAllByRole('article')).toHaveLength(8);
  });

  it('makes unopened one-time catalog details accessible without expanding the bonus browser', async () => {
    const goal = buildChallengeGoal({ origin: 'catalog', progress: '0', catalog_repeatable: false, first_details_opened_at: null });
    const select = vi.fn();
    const { user } = renderWithProviders(<ChallengesFolio goals={[goal]} onSelect={select} />, { withAuth: false });
    const explore = screen.getByRole('region', { name: 'Explore challenges' });
    expect(within(explore).getByRole('article', { name: goal.name })).toBeInTheDocument();
    await user.click(within(explore).getByRole('button', { name: `View ${goal.name}` }));
    expect(select).toHaveBeenCalledWith(goal);
    expect(goal.progress).toBe('0');
  });

  it('filters legacy deadlines in the displayed family zone and leaves unknown dates out of date-filtered results', async () => {
    const goals = [
      buildChallengeGoal({ id: 'legacy:1', name: 'Legacy day', origin: 'legacy', legacy: true, progress: '0', timezone: undefined, ends_at: '2026-10-20T07:00:00Z', qualifying_triggers: null }),
      buildChallengeGoal({ id: 'goal:unknown', name: 'Unknown rule', origin: 'catalog', progress: '0', ends_at: 'invalid-date', what_counts: null, qualifying_triggers: null }),
    ];
    const { user } = renderWithProviders(<ChallengesFolio goals={goals} timezone="America/Phoenix" onSelect={vi.fn()} />, { withAuth: false });
    await user.click(screen.getByText('Browse bonus challenges'));
    expect(screen.getByText('2 of 2 bonus challenges')).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'Unknown rule' })).toHaveTextContent('Qualifying activity unavailable');
    await user.type(screen.getByLabelText('Ends on or before'), '2026-10-19');
    expect(screen.getByText('1 of 2 bonus challenges')).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'Legacy day' })).toBeInTheDocument();
    expect(screen.queryByRole('article', { name: 'Unknown rule' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clear filters' }));
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Qualifying activity' }), 'unknown');
    expect(screen.getByText('2 of 2 bonus challenges')).toBeInTheDocument();
  });

  it('identifies parent goals by server origin even when catalog names match', () => {
    const goals = [
      buildChallengeGoal({ id: 'goal:catalog', origin: 'catalog', progress: '0', name: 'Run 2 miles' }),
      buildChallengeGoal({ id: 'goal:parent', origin: 'parent', progress: '0', name: 'Run 2 miles' }),
    ];
    renderWithProviders(<ChallengesFolio goals={goals} onSelect={vi.fn()} />, { withAuth: false });
    const parent = screen.getByRole('region', { name: 'Parent goals' });
    expect(within(parent).getAllByRole('article')).toHaveLength(1);
    expect(within(parent).getByText('From your parent')).toBeInTheDocument();
    expect(screen.getAllByRole('article', { name: 'Run 2 miles' })).toHaveLength(1);
    expect(screen.queryByRole('progressbar', { name: 'Challenges progress' })).not.toBeInTheDocument();
  });

  it('preserves a pinned parent goal once and uses its actual progress in the shared summary', () => {
    const goal = buildChallengeGoal({ pinned: true, progress: '1', target: '2', timezone: 'America/Phoenix' });
    renderWithProviders(<ChallengesFolio goals={[goal]} pinnedGoal={goal} onSelect={vi.fn()} />, { withAuth: false });
    expect(screen.getAllByRole('article', { name: goal.name })).toHaveLength(1);
    expect(screen.queryByRole('region', { name: 'Parent goals' })).not.toBeInTheDocument();
    screen.getAllByRole('progressbar', { name: 'Challenges progress' }).forEach((bar) => expect(bar).toHaveAttribute('aria-valuenow', '50'));
    expect(within(screen.getByRole('article')).getByText(/Goal period/)).toHaveTextContent('Goal period Oct 12, 2026 – Oct 18, 2026');
  });

  it('opens a background goal for full details without changing its saved progress', async () => {
    const goal = buildChallengeGoal({ origin: 'catalog', progress: '0' });
    const select = vi.fn();
    const { user } = renderWithProviders(<ChallengesFolio goals={[goal]} onSelect={select} />, { withAuth: false });
    await user.click(screen.getByText('Browse bonus challenges'));
    await user.click(await screen.findByRole('button', { name: `View ${goal.name}` }));
    expect(select).toHaveBeenCalledWith(goal);
    expect(goal.progress).toBe('0');
  });

  it('distinguishes repeated completed goals by their saved periods in history', async () => {
    const goals = [
      buildChallengeGoal({ id: 'goal:week-one', name: 'Weekly running', status: 'completed', timezone: 'America/Phoenix', completed_at: '2026-10-19T01:00:00Z' }),
      buildChallengeGoal({ id: 'goal:week-two', name: 'Weekly running', status: 'completed', timezone: 'America/Phoenix', starts_at: '2026-10-19T07:00:00Z', ends_at: '2026-10-26T07:00:00Z', completed_at: '2026-10-26T01:00:00Z' }),
    ];
    const { user } = renderWithProviders(<ChallengesFolio goals={goals} onSelect={vi.fn()} />, { withAuth: false });
    await user.click(screen.getByText('History · 2'));
    const cards = screen.getAllByRole('article', { name: 'Weekly running' });
    expect(cards[0]).toHaveTextContent('Goal period Oct 12, 2026 – Oct 18, 2026');
    expect(cards[0]).toHaveTextContent('Completion recorded Oct 18, 2026');
    expect(cards[1]).toHaveTextContent('Goal period Oct 19, 2026 – Oct 25, 2026');
    expect(cards[1]).toHaveTextContent('Completion recorded Oct 25, 2026');
  });

  it('keeps an incomplete prior cycle in history beside the current parent goal', async () => {
    const goals = [
      buildChallengeGoal({ id: 'goal:prior', name: 'Weekly running', status: 'expired', progress: '1', timezone: 'America/Phoenix', completed_at: null }),
      buildChallengeGoal({ id: 'goal:current', name: 'Weekly running', status: 'active', progress: '0', timezone: 'America/Phoenix', starts_at: '2026-10-19T07:00:00Z', ends_at: '2026-10-26T07:00:00Z' }),
    ];
    const { user } = renderWithProviders(<ChallengesFolio goals={goals} isParent onSelect={vi.fn()} />, { withAuth: false });
    expect(within(screen.getByRole('region', { name: 'Parent goals' })).getByText(/Goal period/)).toHaveTextContent('Goal period Oct 19, 2026 – Oct 25, 2026');
    await user.click(screen.getByText('History · 1'));
    const prior = screen.getAllByRole('article', { name: 'Weekly running' }).find((card) => card.textContent.includes('Period ended'));
    expect(prior).toHaveTextContent('Goal period Oct 12, 2026 – Oct 18, 2026');
    expect(prior).toHaveTextContent('1 / 2 miles');
    expect(prior).not.toHaveTextContent('Completion recorded');
    expect(within(prior).queryByRole('button', { name: /pin/i })).not.toBeInTheDocument();
  });
});
