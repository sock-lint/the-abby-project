import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import SavingsToastStack from './SavingsToastStack';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

describe('SavingsToastStack', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders a toast when a newly-completed goal appears', async () => {
    let goals = [];
    server.use(
      http.get('*/api/savings-goals/', () => HttpResponse.json(goals)),
    );

    render(<SavingsToastStack />);
    // First poll seeds the seen-set — no toast yet.
    await waitFor(() =>
      expect(localStorage.getItem('seenSavingsCompletions')).not.toBeNull(),
    );

    goals = [
      {
        id: 9,
        title: 'Bike',
        target_amount: '100.00',
        is_completed: true,
        completed_at: '2026-04-20T00:00:00Z',
        icon: '🚲',
      },
    ];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });

    await waitFor(() =>
      expect(screen.getByText(/Hoard complete/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Bike · \+200 coins/)).toBeInTheDocument();
  });

  it('dismiss button removes the toast', async () => {
    let goals = [];
    server.use(
      http.get('*/api/savings-goals/', () => HttpResponse.json(goals)),
    );
    render(<SavingsToastStack />);
    await waitFor(() =>
      expect(localStorage.getItem('seenSavingsCompletions')).not.toBeNull(),
    );

    goals = [
      {
        id: 3,
        title: 'Headphones',
        target_amount: '25.00',
        is_completed: true,
        completed_at: '2026-04-20T00:00:00Z',
        icon: '🎧',
      },
    ];
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    await waitFor(() =>
      expect(screen.getByText(/Headphones/)).toBeInTheDocument(),
    );

    // userEvent.setup() would normally manage timers; use the real user here
    // because AnimatePresence is stubbed so click→unmount is synchronous.
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(
      screen.getByRole('button', { name: /dismiss notification/i }),
    );
    await waitFor(() =>
      expect(screen.queryByText(/Headphones/)).not.toBeInTheDocument(),
    );
  });
});
