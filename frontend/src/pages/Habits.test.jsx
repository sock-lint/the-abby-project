import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Habits from './Habits.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildUser } from '../test/factories.js';

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
        <Habits />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Habits', () => {
  it('renders empty state when no habits', async () => {
    renderPage(buildUser(), [
      http.get('*/api/habits/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText((t) => /no habits/i.test(t))).toBeInTheDocument(),
    );
  });

  it('renders a habit row', async () => {
    renderPage(buildUser(), [
      http.get('*/api/habits/', () =>
        HttpResponse.json([
          { id: 1, name: 'Read 20 min', icon: '📖', habit_type: 'positive', strength: 3, color: 'green' },
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/read 20 min/i)).toBeInTheDocument());
  });
});
