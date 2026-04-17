import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Achievements from './Achievements.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
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
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Achievements />
      </AuthProvider>
    </MemoryRouter>,
  );
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
