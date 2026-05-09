import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import TestSection from './TestSection.jsx';
import { server } from '../../test/server.js';

// Stable defaults across tests — the section calls all 3 selector
// endpoints in parallel on mount.
function mountDefaults({ children = [], rewards = [], items = [], checklist = '' } = {}) {
  server.use(
    http.get('*/api/dev/children/', () => HttpResponse.json(children)),
    http.get('*/api/dev/rewards/', () => HttpResponse.json(rewards)),
    http.get('*/api/dev/items/', () => HttpResponse.json(items)),
    http.get('*/api/dev/checklist/', () => HttpResponse.json({ markdown: checklist })),
  );
}

describe('TestSection', () => {
  it('shows the empty-children state when family has no kids', async () => {
    mountDefaults({ children: [] });
    render(<TestSection />);
    await waitFor(() => {
      expect(screen.getByText(/no children in your family yet/i)).toBeInTheDocument();
    });
  });

  it('renders all 8 cards once children load', async () => {
    mountDefaults({
      children: [{ id: 1, username: 'abby', display_label: 'Abby' }],
    });
    render(<TestSection />);
    await waitFor(() => {
      expect(screen.getByText(/Force drop/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Force celebration/i)).toBeInTheDocument();
    expect(screen.getByText(/Set streak/i)).toBeInTheDocument();
    expect(screen.getByText(/Set pet happiness/i)).toBeInTheDocument();
    expect(screen.getByText(/Expire journal entry/i)).toBeInTheDocument();
    expect(screen.getByText(/Set reward stock/i)).toBeInTheDocument();
    expect(screen.getByText(/Reset day counters/i)).toBeInTheDocument();
    expect(screen.getByText(/Tick perfect day/i)).toBeInTheDocument();
  });

  it('shows a boot-error empty state when ALL three selector endpoints fail', async () => {
    server.use(
      http.get('*/api/dev/children/', () => new HttpResponse(null, { status: 403 })),
      http.get('*/api/dev/rewards/', () => new HttpResponse(null, { status: 403 })),
      http.get('*/api/dev/items/', () => new HttpResponse(null, { status: 403 })),
      http.get('*/api/dev/checklist/', () => new HttpResponse(null, { status: 403 })),
    );
    render(<TestSection />);
    await waitFor(() => {
      expect(screen.getByText(/could not reach \/api\/dev/i)).toBeInTheDocument();
    });
  });

  it('Force drop card POSTs to /api/dev/force-drop/ with the form values', async () => {
    mountDefaults({
      children: [{ id: 7, username: 'abby', display_label: 'Abby' }],
    });

    const calls = [];
    server.use(
      http.post('*/api/dev/force-drop/', async ({ request }) => {
        const body = await request.json();
        calls.push({ body });
        return HttpResponse.json({
          user: 'abby',
          item: { id: 1, slug: 'lucky-coin', name: 'Lucky Coin', rarity: 'legendary' },
          count: 1,
          salvaged: false,
        });
      }),
    );

    const user = userEvent.setup();
    render(<TestSection />);

    const dropCard = (await screen.findByText('Force drop')).closest('div');
    const fire = within(dropCard.parentElement).getByRole('button', { name: /drop it/i });
    await user.click(fire);

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.user_id).toBe(7);
    expect(calls[0].body.rarity).toBe('legendary');
    expect(calls[0].body.salvage).toBe(false);
  });

  it('Set streak card POSTs to /api/dev/set-streak/ with the days field', async () => {
    mountDefaults({
      children: [{ id: 7, username: 'abby', display_label: 'Abby' }],
    });

    const calls = [];
    server.use(
      http.post('*/api/dev/set-streak/', async ({ request }) => {
        const body = await request.json();
        calls.push({ body });
        return HttpResponse.json({
          user: 'abby',
          login_streak: 29,
          longest_login_streak: 29,
          perfect_days_count: 0,
          last_active_date: '2026-05-09',
        });
      }),
    );

    const user = userEvent.setup();
    render(<TestSection />);
    await screen.findByText(/Set streak/i);

    const setStreakCard = (await screen.findByText('Set streak')).closest('div');
    const fire = within(setStreakCard.parentElement).getByRole('button', { name: /^Set$/i });
    await user.click(fire);

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.user_id).toBe(7);
    expect(calls[0].body.days).toBe(29);
  });
});
