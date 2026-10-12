import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import QuestsHub from './index.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildUser } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('QuestsHub', () => {
  it('renders the Tasks hub with Homework selected by default', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/projects/', () => HttpResponse.json([])),
    );
    render(
      <MemoryRouter>
        <AuthProvider>
          <QuestsHub />
        </AuthProvider>
      </MemoryRouter>,
    );
    // Hub no longer renders an h1; check the tablist aria-label instead.
    await waitFor(() =>
      expect(screen.getByRole('tablist', { name: /tasks sections/i })).toBeInTheDocument(),
    );
    expect(screen.getAllByText(/projects/i).length).toBeGreaterThan(0);
  });

  it('exposes seven tabs (Homework · Chores · Habits · Movement · Projects · 3D Printing · Challenges)', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/projects/', () => HttpResponse.json([])),
    );
    render(
      <MemoryRouter>
        <AuthProvider>
          <QuestsHub />
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole('tab', { name: /projects/i })).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: /chores/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /homework/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /habits/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /movement/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /challenges/i })).toBeInTheDocument();
    // The Forge slug is the binding contract for the seven print_* notification
    // types, which all deep-link to /quests?tab=forge.
    expect(screen.getByRole('tab', { name: /3d printing/i })).toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(7);
  });
});
