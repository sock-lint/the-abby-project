import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor, act } from '../test/render';
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
beforeEach(() => { server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser()))); });

describe('Grouped challenge receipts', () => {
  it('shows multiple matching goals and exact completed awards from one stable activity receipt', async () => {
    renderWithProviders(<QuestProgressToastStack />, { pulse: emptyPulse({ challenge_receipts: [receipt()] }) });
    expect(await screen.findByText('Challenge progress')).toBeInTheDocument();
    expect(screen.getByText(/Run this week · Completed/)).toHaveTextContent('+10 coins · +0 XP');
    expect(screen.getByText('Move regularly · 3 / 5 activities')).toBeInTheDocument();
    expect(screen.getAllByText('Challenge progress')).toHaveLength(1);
  });


  it('keeps the three newest completions from a newest-first backlog and dedupes later reads', async () => {
    const backlog = [5, 4, 3, 2, 1].map((id) => ({
      id: `activity:${id}`, daily_bonus: null,
      goals: [{ id: `goal:${id}`, name: `Finished goal ${id}`, progress: '1', target: '1', unit: 'actions', completed: true, rewards: { coins: id, xp: 0, items: [] } }],
    }));
    const { user, beat } = renderWithProviders(<QuestProgressToastStack />, { pulse: emptyPulse({ challenge_receipts: backlog }) });
    expect(await screen.findByText(/Finished goal 5 · Completed/)).toBeInTheDocument();
    expect(screen.getByText(/Finished goal 4 · Completed/)).toBeInTheDocument();
    expect(screen.getByText(/Finished goal 3 · Completed/)).toBeInTheDocument();
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
    expect(await screen.findByText(/Run this week · Completed/)).toBeInTheDocument();
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
