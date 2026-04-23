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
  it('renders the quests hub default ventures tab', async () => {
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
    await waitFor(() => expect(screen.getByText('Quests')).toBeInTheDocument());
    expect(screen.getAllByText(/ventures/i).length).toBeGreaterThan(0);
  });

  it('exposes five tabs (Ventures · Duties · Study · Rituals · Movement) — no Trials tab', async () => {
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
    await waitFor(() => expect(screen.getByRole('tab', { name: /ventures/i })).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: /duties/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /study/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /rituals/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /movement/i })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /trials/i })).toBeNull();
    expect(screen.getAllByRole('tab')).toHaveLength(5);
  });
});
