import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Achievements from './Achievements.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildParent, buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(
  { user = buildUser(), handlers = [], initialRoute = '/achievements' } = {},
) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <AuthProvider>
        <Achievements />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Achievements', () => {
  it('renders error block when summary fetch fails', async () => {
    renderPage({
      handlers: [
        http.get('*/api/achievements/summary/', () =>
          HttpResponse.json({ error: 'x' }, { status: 500 }),
        ),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument(),
    );
  });

  it('defaults to the Atlas tab and renders the skill tree', async () => {
    renderPage({
      handlers: [
        http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
        http.get('*/api/badges/', () => HttpResponse.json([])),
        http.get('*/api/categories/', () =>
          HttpResponse.json([{ id: 1, name: 'Woodworking', icon: '🪵' }]),
        ),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Atlas' })).toHaveAttribute('aria-selected', 'true'),
    );
    expect(screen.getByRole('tab', { name: 'Sigils' })).toHaveAttribute('aria-selected', 'false');
  });

  it('renders the sigils view when ?tab=sigils is present', async () => {
    renderPage({
      initialRoute: '/achievements?tab=sigils',
      handlers: [
        http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
        http.get('*/api/badges/', () =>
          HttpResponse.json([{ id: 1, name: 'First Stitch', rarity: 'common', icon: '🧵' }]),
        ),
        http.get('*/api/categories/', () => HttpResponse.json([])),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Sigils' })).toHaveAttribute('aria-selected', 'true'),
    );
    expect(screen.getByText('First Stitch')).toBeInTheDocument();
    expect(screen.getByText(/0 of 1 sigils sealed/i)).toBeInTheDocument();
  });

  it('falls back to Atlas when ?tab is unknown', async () => {
    renderPage({
      initialRoute: '/achievements?tab=bogus',
      handlers: [
        http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
        http.get('*/api/badges/', () => HttpResponse.json([])),
        http.get('*/api/categories/', () => HttpResponse.json([])),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Atlas' })).toHaveAttribute('aria-selected', 'true'),
    );
  });

  it('switches from Atlas to Sigils on click', async () => {
    const user = userEvent.setup();
    renderPage({
      handlers: [
        http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
        http.get('*/api/badges/', () =>
          HttpResponse.json([{ id: 1, name: 'First Stitch', rarity: 'common', icon: '🧵' }]),
        ),
        http.get('*/api/categories/', () => HttpResponse.json([])),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Atlas' })).toHaveAttribute('aria-selected', 'true'),
    );
    await user.click(screen.getByRole('tab', { name: 'Sigils' }));
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Sigils' })).toHaveAttribute('aria-selected', 'true'),
    );
    expect(screen.getByText('First Stitch')).toBeInTheDocument();
  });

  it('parent sees manage panel tab', async () => {
    renderPage({
      user: buildParent(),
      handlers: [
        http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Manage' })).toBeInTheDocument(),
    );
  });
});
