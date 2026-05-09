import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Badges from './Badges.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage({ user = buildUser(), handlers = [] } = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Badges />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Badges page', () => {
  it('renders an error block when summary fetch fails', async () => {
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

  it('renders the incipit band, sealed-count, and collection chapters', async () => {
    renderPage({
      handlers: [
        http.get('*/api/achievements/summary/', () =>
          HttpResponse.json({
            badges_earned: [
              {
                badge: {
                  id: 2,
                  name: 'Perfect Joinery',
                  rarity: 'rare',
                  icon: '🏆',
                  criterion_type: 'milestones_completed',
                  criterion_value: 10,
                },
                earned_at: '2026-04-10',
              },
            ],
          }),
        ),
        http.get('*/api/badges/', () =>
          HttpResponse.json([
            { id: 1, name: 'First Stitch', rarity: 'common', icon: '🧵', criterion_type: 'first_project' },
            {
              id: 2,
              name: 'Perfect Joinery',
              rarity: 'rare',
              icon: '🏆',
              criterion_type: 'milestones_completed',
              criterion_value: 10,
            },
          ]),
        ),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Sigil Case' })).toBeInTheDocument(),
    );
    // Incipit shows the overall sealed count; Ventures chapter shows its own.
    // Both render "1 of 2", so match the multiple.
    const sealedCounts = screen.getAllByText(/1 of 2/);
    expect(sealedCounts.length).toBeGreaterThanOrEqual(2);
    // Both chapter regions present
    expect(screen.getByRole('region', { name: 'Ventures' })).toBeInTheDocument();
    // Both sigils rendered
    expect(screen.getByText('Perfect Joinery')).toBeInTheDocument();
    expect(screen.getByText('First Stitch')).toBeInTheDocument();
  });

  it('opens a detail sheet when a sigil is clicked', async () => {
    const user = userEvent.setup();
    renderPage({
      handlers: [
        http.get('*/api/achievements/summary/', () =>
          HttpResponse.json({
            badges_earned: [
              {
                badge: {
                  id: 2,
                  name: 'Perfect Joinery',
                  rarity: 'rare',
                  icon: '🏆',
                  criterion_type: 'milestones_completed',
                  criterion_value: 10,
                },
                earned_at: '2026-04-10',
              },
            ],
          }),
        ),
        http.get('*/api/badges/', () =>
          HttpResponse.json([
            {
              id: 2,
              name: 'Perfect Joinery',
              rarity: 'rare',
              icon: '🏆',
              criterion_type: 'milestones_completed',
              criterion_value: 10,
            },
          ]),
        ),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /Perfect Joinery/ })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /Perfect Joinery/ }));
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: 'Perfect Joinery' })).toBeInTheDocument(),
    );
  });

  it('renders empty state when no badges exist', async () => {
    renderPage({
      handlers: [
        http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
        http.get('*/api/badges/', () => HttpResponse.json([])),
      ],
    });
    await waitFor(() =>
      expect(screen.getByText(/no badges have been forged yet/i)).toBeInTheDocument(),
    );
  });

  it('filters badges by name when the user types in the search', async () => {
    const user = userEvent.setup();
    renderPage({
      handlers: [
        http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
        http.get('*/api/badges/', () =>
          HttpResponse.json([
            { id: 1, name: 'First Stitch', rarity: 'common', icon: '🧵', criterion_type: 'first_project' },
            {
              id: 2, name: 'Perfect Joinery', rarity: 'rare', icon: '🏆',
              criterion_type: 'milestones_completed', criterion_value: 10,
            },
          ]),
        ),
      ],
    });
    await waitFor(() => expect(screen.getByText('First Stitch')).toBeInTheDocument());

    const search = screen.getByRole('searchbox', { name: /filter badges/i });
    await user.type(search, 'joinery');

    expect(screen.queryByText('First Stitch')).not.toBeInTheDocument();
    expect(screen.getByText('Perfect Joinery')).toBeInTheDocument();
  });
});
