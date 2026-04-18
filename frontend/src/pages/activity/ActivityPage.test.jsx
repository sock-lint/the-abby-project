import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ActivityPage from './ActivityPage.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildParent, buildUser } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ActivityPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

function buildEvent(over = {}) {
  return {
    id: 1,
    occurred_at: new Date().toISOString(),
    category: 'award',
    event_type: 'award.coins',
    summary: '+10 coins',
    actor: null,
    subject: { id: 2, display_name: 'Abby', role: 'child' },
    target: null,
    coins_delta: 10,
    money_delta: null,
    xp_delta: null,
    context: {
      breakdown: [
        { label: 'base', value: 5, op: '×' },
        { label: 'multiplier', value: 2, op: '=' },
      ],
      extras: {},
    },
    correlation_id: null,
    ...over,
  };
}

describe('ActivityPage', () => {
  it('renders empty state when there are no events', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([])),
      http.get('*/api/activity/', () =>
        HttpResponse.json({ results: [], next: null, previous: null })),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/no activity yet/i)).toBeInTheDocument(),
    );
  });

  it('renders an event row with summary and event_type slug', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () =>
        HttpResponse.json([buildUser({ id: 2, display_name: 'Abby' })]),
      ),
      http.get('*/api/activity/', () =>
        HttpResponse.json({
          results: [buildEvent({ summary: 'Hourly coins: Blueberry Bush' })],
          next: null,
          previous: null,
        })),
    );
    renderPage();
    await waitFor(() =>
      expect(screen.getByText('Hourly coins: Blueberry Bush')).toBeInTheDocument(),
    );
    expect(screen.getByText('award.coins')).toBeInTheDocument();
    // Coin pill is the only +10 coins node
    expect(screen.getByText(/\+10 coins/i)).toBeInTheDocument();
  });

  it('reveals the math breakdown on click', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([])),
      http.get('*/api/activity/', () =>
        HttpResponse.json({
          results: [buildEvent()],
          next: null,
          previous: null,
        })),
    );
    const user = userEvent.setup();
    renderPage();

    const toggle = await screen.findByRole('button', { name: /show math/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('base')).toBeInTheDocument();
    expect(screen.getByText('multiplier')).toBeInTheDocument();
  });

  it('sends the selected category slug as a query param', async () => {
    const calls = [];
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([])),
      http.get('*/api/activity/', ({ request }) => {
        calls.push(new URL(request.url).searchParams.get('category'));
        return HttpResponse.json({ results: [], next: null, previous: null });
      }),
    );
    const user = userEvent.setup();
    renderPage();

    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /approvals/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /approvals/i }));
    await waitFor(() => expect(calls).toContain('approval'));
  });
});
