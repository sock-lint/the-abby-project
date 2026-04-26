import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import BestiaryHub from './index.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildUser } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('BestiaryHub', () => {
  function stubAll() {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], total_possible: 0 })),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      http.get('*/api/pets/codex/', () =>
        HttpResponse.json({ species: [], potions: [], totals: { species: 0, discovered_species: 0, mounts_possible: 0, mounts_owned: 0 } }),
      ),
    );
  }

  it('renders the bestiary hub', async () => {
    stubAll();
    render(
      <MemoryRouter>
        <AuthProvider>
          <BestiaryHub />
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('Bestiary')).toBeInTheDocument());
  });

  it('exposes Companions, Mounts, Codex, and Hatchery tabs', async () => {
    stubAll();
    render(
      <MemoryRouter>
        <AuthProvider>
          <BestiaryHub />
        </AuthProvider>
      </MemoryRouter>,
    );
    await screen.findByRole('tab', { name: 'Companions' });
    expect(screen.getByRole('tab', { name: 'Mounts' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Codex' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Hatchery' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Party' })).toBeNull();
    expect(screen.queryByRole('tab', { name: 'Satchel' })).toBeNull();
  });
});
