import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor, act, within } from '../test/render';
import { useLocation } from 'react-router-dom';
import { server } from '../test/server';
import { buildUser, buildParent } from '../test/factories';
import { emptyPulse } from '../test/pulseFixtures';
import QuestProgressToastStack from './QuestProgressToastStack';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});
const receipt = (id = 'activity:9') => ({
  id, goals: [
    { id: 'goal:11', name: 'Run this week', progress: '2', target: '2', unit: 'mi', completed: true, rewards: { coins: 10, xp: 0, items: [] } },
    { id: 'goal:12', name: 'Move regularly', progress: '3', target: '5', unit: 'actions', completed: false, rewards: null },
  ], daily_bonus: null,
});
const largeReceipt = (id = 'activity:20') => ({
  id,
  goals: Array.from({ length: 20 }, (_, index) => ({
    id: `goal:${id}:${index}`, name: `Challenge ${index + 1}${index === 18 ? ' with a long descriptive name'.repeat(6) : ''}`,
    progress: index >= 18 ? '10' : '1', target: '10', unit: 'actions', completed: index >= 18,
    rewards: index >= 18 ? { coins: 7, xp: 3, items: [] } : null,
  })),
  daily_bonus: { awarded: true, coins_awarded: 2, xp_awarded: 5 },
});
function LocationProbe() {
  const location = useLocation();
  return <output aria-label="Current page">{location.pathname}{location.search}</output>;
}
beforeEach(() => { server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser()))); });

describe('Grouped challenge receipts', () => {
  it('shows multiple matching goals and exact completed awards from one stable activity receipt', async () => {
    renderWithProviders(<QuestProgressToastStack />, { pulse: emptyPulse({ challenge_receipts: [receipt()] }) });
    expect(await screen.findByText('Challenge progress')).toBeInTheDocument();
    expect(screen.getByText('Run this week').closest('li')).toHaveTextContent('Completed · +10 coins · +0 XP');
    expect(screen.getByText('Move regularly').closest('li')).toHaveTextContent('3 / 5 activities');
    expect(screen.getAllByText('Challenge progress')).toHaveLength(1);
  });

  it('summarizes twenty matching goals, prioritizes completions, and retains full accessible names and paid bonus', async () => {
    const update = largeReceipt();
    renderWithProviders(<QuestProgressToastStack />, { pulse: emptyPulse({ challenge_receipts: [update] }) });
    await screen.findByText('Challenge progress');
    expect(screen.getAllByText(/Challenge \d+/)).toHaveLength(3);
    const rows = screen.getAllByRole('listitem');
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining(update.goals[18].name),
      expect.stringContaining('Challenge 20'),
      expect.stringContaining('Challenge 1'),
    ]);
    expect(within(rows[0]).getByText(update.goals[18].name)).toHaveAttribute('title', update.goals[18].name);
    expect(rows[0]).toHaveTextContent('Completed · +7 coins · +3 XP');
    expect(screen.queryByText('Challenge 2', { exact: true })).not.toBeInTheDocument();
    expect(screen.getByText('+17 more challenges')).toBeInTheDocument();
    expect(screen.getByText("Today's bonus · +2 coins · +5 XP")).toBeInTheDocument();
    expect(update.goals).toHaveLength(20);
    expect(update.goals[0].name).toBe('Challenge 1');
  });

  it('keeps three large receipts individually dismissible without expanding their summaries', async () => {
    const { user } = renderWithProviders(<QuestProgressToastStack inline />, {
      pulse: emptyPulse({ challenge_receipts: [largeReceipt('activity:3'), largeReceipt('activity:2'), largeReceipt('activity:1')] }),
    });
    await screen.findAllByText('Challenge progress');
    const stack = screen.getByRole('region', { name: 'Challenge updates' });
    expect(stack).toHaveAttribute('tabindex', '0');
    expect(within(stack).getAllByRole('listitem')).toHaveLength(9);
    expect(within(stack).getAllByText('+17 more challenges')).toHaveLength(3);
    expect(within(stack).getAllByRole('link', { name: 'View challenges' })).toHaveLength(3);
    for (const button of within(stack).getAllByRole('button', { name: 'Dismiss notification' })) await user.click(button);
    expect(screen.queryByRole('region', { name: 'Challenge updates' })).not.toBeInTheDocument();
  });

  it('opens the full Challenges list from the remaining-goal summary', async () => {
    const { user } = renderWithProviders(<><QuestProgressToastStack /><LocationProbe /></>, {
      pulse: emptyPulse({ challenge_receipts: [largeReceipt()] }),
    });
    const link = await screen.findByRole('link', { name: 'View challenges' });
    expect(link).toHaveAttribute('href', '/quests?tab=trials');
    await user.click(link);
    expect(screen.getByRole('status', { name: 'Current page' })).toHaveTextContent('/quests?tab=trials');
  });


  it('keeps the three newest completions from a newest-first backlog and dedupes later reads', async () => {
    const backlog = [5, 4, 3, 2, 1].map((id) => ({
      id: `activity:${id}`, daily_bonus: null,
      goals: [{ id: `goal:${id}`, name: `Finished goal ${id}`, progress: '1', target: '1', unit: 'actions', completed: true, rewards: { coins: id, xp: 0, items: [] } }],
    }));
    const { user, beat } = renderWithProviders(<QuestProgressToastStack />, { pulse: emptyPulse({ challenge_receipts: backlog }) });
    expect(await screen.findByText('Finished goal 5')).toBeInTheDocument();
    expect(screen.getByText('Finished goal 4')).toBeInTheDocument();
    expect(screen.getByText('Finished goal 3')).toBeInTheDocument();
    expect(screen.queryByText(/Finished goal 2/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Finished goal 1/)).not.toBeInTheDocument();
    expect(screen.getAllByText('Challenge progress')).toHaveLength(3);
    for (const button of screen.getAllByRole('button', { name: 'Dismiss notification' })) await user.click(button);
    // The same persisted receipt IDs can arrive through successive reads.
    beat(emptyPulse({ challenge_receipts: [...backlog] }));
    await waitFor(() => expect(screen.queryByText('Challenge progress')).not.toBeInTheDocument());
  });

  it('does not replay dismissed receipts across polling or remounting', async () => {
    const pulse = emptyPulse({ challenge_receipts: [receipt()] });
    const { user, beat, unmount } = renderWithProviders(<QuestProgressToastStack />, { pulse });
    await screen.findByText('Challenge progress');
    await user.click(screen.getByRole('button', { name: 'Dismiss notification' }));
    beat(emptyPulse({ challenge_receipts: [receipt()] }));
    await waitFor(() => expect(screen.queryByText('Challenge progress')).not.toBeInTheDocument());
    unmount();
    renderWithProviders(<QuestProgressToastStack />, { pulse });
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryByText('Challenge progress')).not.toBeInTheDocument();
  });

  it('can show completed goals that no longer appear among active goals', async () => {
    const { beat } = renderWithProviders(<QuestProgressToastStack />, { pulse: emptyPulse() });
    beat(emptyPulse({ active_quest: null, challenge_receipts: [receipt()] }));
    expect(await screen.findByText('Run this week')).toBeInTheDocument();
  });

  it('stays silent for parents', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
    renderWithProviders(<QuestProgressToastStack />, { pulse: emptyPulse({ challenge_receipts: [receipt()] }) });
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryByText('Challenge progress')).not.toBeInTheDocument();
  });

  it('never creates an award from progress snapshots without receipts', async () => {
    renderWithProviders(<QuestProgressToastStack />, { pulse: emptyPulse({ active_quest: { id: 1, current_progress: 100, progress_percent: 100 } }) });
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryByText('Challenge progress')).not.toBeInTheDocument();
  });
});
