import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import TreasuryHub from './index.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildUser } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('TreasuryHub', () => {
  it('renders the treasury hub default coffers tab', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/balance/', () =>
        HttpResponse.json({ balance: 0, breakdown: {}, recent_transactions: [] }),
      ),
    );
    render(
      <MemoryRouter>
        <AuthProvider>
          <TreasuryHub />
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText('Treasury')).toBeInTheDocument());
  });
});
