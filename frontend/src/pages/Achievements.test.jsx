import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Achievements from './Achievements.jsx';
import { server } from '../test/server.js';
import { renderWithProviders } from '../test/render.jsx';
import { buildParent, buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage({ user = buildUser(), handlers = [] } = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return renderWithProviders(<Achievements />);
}

describe('Achievements (Skills page)', () => {
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

  it('renders the Skills header and skill tree for a child', async () => {
    renderPage({
      handlers: [
        http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
        http.get('*/api/categories/', () =>
          HttpResponse.json([{ id: 1, name: 'Woodworking', icon: '🪵' }]),
        ),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Skills' })).toBeInTheDocument(),
    );
    // Child should NOT see View | Manage toggle.
    expect(screen.queryByRole('tab', { name: 'Manage' })).toBeNull();
    // Category pennant renders as a tab.
    expect(screen.getByRole('tab', { name: /Woodworking/ })).toBeInTheDocument();
  });

  it('reveals the search and filters skills inside the loaded folio', async () => {
    const user = userEvent.setup();
    renderPage({
      handlers: [
        http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
        http.get('*/api/categories/', () =>
          HttpResponse.json([{ id: 1, name: 'Woodworking', icon: '🪵' }]),
        ),
        http.get('*/api/skills/tree/1/', () =>
          HttpResponse.json({
            category: { id: 1, name: 'Woodworking', icon: '🪵' },
            summary: { level: 1, total_xp: 50 },
            subjects: [{
              id: 10,
              name: 'Joinery',
              skills: [
                { id: 100, name: 'Mortise and Tenon', level: 1, xp_points: 10, unlocked: true },
                { id: 101, name: 'Dovetail', level: 0, xp_points: 0, unlocked: true },
              ],
            }],
            skills: [],
          }),
        ),
      ],
    });
    // No search before a tome is opened.
    expect(screen.queryByRole('searchbox', { name: /filter skills/i })).toBeNull();

    await user.click(await screen.findByRole('tab', { name: /Woodworking/ }));
    await waitFor(() => expect(screen.getByText('Mortise and Tenon')).toBeInTheDocument());

    const search = screen.getByRole('searchbox', { name: /filter skills/i });
    await user.type(search, 'dovetail');

    await waitFor(() => {
      expect(screen.queryByText('Mortise and Tenon')).not.toBeInTheDocument();
      expect(screen.getByText('Dovetail')).toBeInTheDocument();
    });
  });

  it('parent sees the View | Manage toggle', async () => {
    renderPage({
      user: buildParent(),
      handlers: [
        http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
        http.get('*/api/categories/', () => HttpResponse.json([])),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Manage' })).toBeInTheDocument(),
    );
    expect(screen.getByRole('tab', { name: 'View' })).toHaveAttribute('aria-selected', 'true');
  });
});
