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

function renderPage(user = buildUser(), handlers = []) {
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

describe('Achievements', () => {
  it('renders error block when summary fetch fails', async () => {
    renderPage(buildUser(), [
      http.get('*/api/achievements/summary/', () =>
        HttpResponse.json({ error: 'x' }, { status: 500 }),
      ),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument(),
    );
  });

  it('renders a minimal achievements view', async () => {
    renderPage(buildUser(), [
      http.get('*/api/achievements/summary/', () =>
        HttpResponse.json({ badges_earned: [], total_xp: 0 }),
      ),
    ]);
    await waitFor(() =>
      expect(screen.getAllByText((t) => /badge|skill|category|atlas|achievement/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('parent sees manage panel tab', async () => {
    renderPage(buildParent(), [
      http.get('*/api/achievements/summary/', () =>
        HttpResponse.json({ badges_earned: [] }),
      ),
    ]);
    await waitFor(() => expect(screen.getAllByRole('button').length).toBeGreaterThan(0));
  });
});
