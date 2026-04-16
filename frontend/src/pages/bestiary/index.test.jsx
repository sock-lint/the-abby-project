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
  it('renders the bestiary hub', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], total_possible: 0 })),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    render(
      <MemoryRouter>
        <AuthProvider>
          <BestiaryHub />
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('Bestiary')).toBeInTheDocument());
  });
});
