import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Quests from './Quests.jsx';
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
        <Quests />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Quests', () => {
  it('renders empty current state', async () => {
    renderPage(buildUser(), [
      http.get('*/api/quests/active/', () => HttpResponse.json(null)),
      http.get('*/api/quests/available/', () => HttpResponse.json([])),
      http.get('*/api/quests/history/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getAllByText((t) => /quest|trial/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('switches to history tab', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/quests/active/', () => HttpResponse.json(null)),
      http.get('*/api/quests/available/', () => HttpResponse.json([])),
      http.get('*/api/quests/history/', () =>
        HttpResponse.json([{ id: 1, status: 'completed', completed_at: '2026-04-10', definition: { name: 'Old Quest', quest_type: 'boss' } }]),
      ),
    ]);
    const historyTab = await screen.findByRole('button', { name: /history/i });
    await user.click(historyTab);
    await waitFor(() => expect(screen.getByText(/old quest/i)).toBeInTheDocument());
  });
});
