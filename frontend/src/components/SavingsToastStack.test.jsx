import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/render';
import { emptyPulse } from '../test/pulseFixtures.js';
import SavingsToastStack from './SavingsToastStack';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const goal = (over = {}) => ({
  id: 9,
  title: 'Bike',
  target_amount: '100.00',
  is_completed: true,
  completed_at: '2026-04-20T00:00:00Z',
  icon: '🚲',
  ...over,
});

describe('SavingsToastStack', () => {
  beforeEach(() => {
    localStorage.clear();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders a toast when a newly-completed goal appears', async () => {
    // First beat seeds the seen-set — a goal already complete at page load
    // must not re-toast.
    const { beat } = renderWithProviders(<SavingsToastStack />, { pulse: emptyPulse() });
    await waitFor(() =>
      expect(localStorage.getItem('seenSavingsCompletions')).not.toBeNull(),
    );

    beat(emptyPulse({ savings_goals: [goal()] }));

    await waitFor(() =>
      expect(screen.getByText(/Hoard complete/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Bike · \+200 coins/)).toBeInTheDocument();
  });

  it('does not re-toast a goal that was already complete on the first beat', async () => {
    renderWithProviders(<SavingsToastStack />, {
      pulse: emptyPulse({ savings_goals: [goal()] }),
    });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/Hoard complete/i)).not.toBeInTheDocument();
  });

  it('dismiss button removes the toast', async () => {
    const { beat } = renderWithProviders(<SavingsToastStack />, { pulse: emptyPulse() });
    await waitFor(() =>
      expect(localStorage.getItem('seenSavingsCompletions')).not.toBeNull(),
    );

    beat(emptyPulse({
      savings_goals: [goal({ id: 3, title: 'Headphones', target_amount: '25.00', icon: '🎧' })],
    }));
    await waitFor(() => expect(screen.getByText(/Headphones/)).toBeInTheDocument());

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /dismiss notification/i }));
    await waitFor(() =>
      expect(screen.queryByText(/Headphones/)).not.toBeInTheDocument(),
    );
  });
});
