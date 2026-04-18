import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import QuickActionsFab from './QuickActionsFab.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildUser } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function renderFab(handlers = [], user = buildUser()) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <QuickActionsFab />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('QuickActionsFab', () => {
  it('renders the default Quick label when not clocked in', async () => {
    renderFab([
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'inactive' })),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /quick actions/i })).toBeInTheDocument(),
    );
    expect(screen.getByText(/quick/i)).toBeInTheDocument();
  });

  it('shows a running timer label when clocked in', async () => {
    renderFab([
      http.get('*/api/clock/', () =>
        HttpResponse.json({
          status: 'active',
          clock_in: new Date(Date.now() - 65_000).toISOString(),
        }),
      ),
    ]);
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /quick actions \(clocked in\)/i }),
      ).toBeInTheDocument(),
    );
    // MM:SS format when under an hour — around 01:0x.
    expect(screen.getByText(/^0?1:0\d$/)).toBeInTheDocument();
  });

  it('clicking the FAB opens the QuickActionsSheet dialog', async () => {
    const u = userEvent.setup();
    renderFab([
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'inactive' })),
    ]);

    const fab = await screen.findByRole('button', { name: /quick actions/i });
    await u.click(fab);

    await waitFor(() =>
      expect(screen.getByRole('dialog')).toBeInTheDocument(),
    );
  });
});
