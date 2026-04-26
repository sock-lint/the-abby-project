import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Mounts from './Mounts.jsx';
import { AuthProvider } from '../../../hooks/useApi.js';
import { server } from '../../../test/server.js';
import { spyHandler } from '../../../test/spy.js';
import { buildUser } from '../../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

const RECENT_BRED = new Date(Date.now() - 1000).toISOString();

const MOUNTS = [
  {
    id: 9,
    species: { name: 'Griffon', sprite_key: 'griffon', icon: '🦅' },
    potion: { name: 'Sky', slug: 'sky', rarity: 'rare' },
    is_active: true,
    last_bred_at: null,
  },
  {
    id: 10,
    species: { name: 'Wolf', sprite_key: 'wolf', icon: '🐺' },
    potion: { name: 'Earth', slug: 'earth', rarity: 'common' },
    is_active: false,
    last_bred_at: RECENT_BRED,
  },
];

function renderPage(handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Mounts />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Mounts tab', () => {
  it('renders empty state when no mounts', async () => {
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [], total_possible: 48 }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/no mounts yet/i)).toBeInTheDocument());
  });

  it('renders mounts and counts each filter pill', async () => {
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: MOUNTS, total_possible: 48 }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/Griffon/)).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: /All \(2\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Active \(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Ready to breed \(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /On cooldown \(1\)/ })).toBeInTheDocument();
  });

  it('Ready to breed filter shows only mounts off cooldown', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: MOUNTS, total_possible: 48 }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/Griffon/)).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /Ready to breed/ }));
    await waitFor(() => {
      expect(screen.getByText(/Griffon/)).toBeInTheDocument();
      expect(screen.queryByText(/Wolf/)).toBeNull();
    });
  });

  it('On cooldown filter shows only mounts within breeding window', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: MOUNTS, total_possible: 48 }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/Griffon/)).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /On cooldown/ }));
    await waitFor(() => {
      expect(screen.queryByText(/Griffon/)).toBeNull();
      expect(screen.getByText(/Wolf/)).toBeInTheDocument();
    });
  });

  it('Saddle up POSTs to mount activate endpoint', async () => {
    const user = userEvent.setup();
    const activate = spyHandler('post', /\/api\/mounts\/\d+\/activate\/$/, { ok: true });
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [MOUNTS[1]], total_possible: 48 }),
      ),
      activate.handler,
    ]);
    await waitFor(() => expect(screen.getByText(/Wolf/)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /saddle up/i }));
    await waitFor(() => expect(activate.calls).toHaveLength(1));
    expect(activate.calls[0].url).toMatch(/\/mounts\/10\/activate\/$/);
  });
});
