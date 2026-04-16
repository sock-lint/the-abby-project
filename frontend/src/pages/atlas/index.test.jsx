import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AtlasHub from './index.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildUser } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('AtlasHub', () => {
  it('renders the Atlas hub with the Skills tab default', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
    );
    render(
      <MemoryRouter>
        <AuthProvider>
          <AtlasHub />
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('Atlas')).toBeInTheDocument());
    expect(screen.getAllByText(/skills/i).length).toBeGreaterThan(0);
  });
});
