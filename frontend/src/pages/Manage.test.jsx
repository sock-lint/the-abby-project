import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Manage from './Manage.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildParent, buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Manage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Manage', () => {
  it('renders the children tab by default', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () =>
        HttpResponse.json([buildUser({ id: 3, display_name: 'Abby' })]),
      ),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText(/children/i)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText('Abby')).toBeInTheDocument());
  });

  it('switches to the templates tab', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/templates/', () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    renderPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /templates/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /templates/i }));
    await waitFor(() =>
      expect(screen.getAllByText((t) => /template/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('switches to the codex tab', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /codex/i }));
    await waitFor(() =>
      expect(screen.getAllByText((t) => /codex/i.test(t)).length).toBeGreaterThan(0),
    );
  });
});
