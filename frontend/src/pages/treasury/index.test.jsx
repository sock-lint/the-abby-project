import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import TreasuryHub from './index.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildParent, buildUser } from '../../test/factories.js';
import userEvent from '@testing-library/user-event';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('TreasuryHub', () => {
  it('keeps family rewards focused on shop, print decisions and family money', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
    render(<MemoryRouter><AuthProvider><TreasuryHub /></AuthProvider></MemoryRouter>);
    await waitFor(() => expect(screen.queryByRole('tab', { name: 'Inventory' })).toBeNull());
    expect(screen.getByRole('tab', { name: 'Payments' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Timecards' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Shop' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Savings goals' })).toBeNull();
  });

  it('opens print requests alongside the reward shop', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={['/treasury?tab=bazaar']}>
      <AuthProvider><TreasuryHub /></AuthProvider>
    </MemoryRouter>);
    await user.click(await screen.findByRole('tab', { name: '3D Prints' }));
    expect(await screen.findByRole('heading', { level: 1, name: '3D Prints' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ask for a print' })).toBeInTheDocument();
  });

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
    // Hub no longer renders an h1 — the active tab page (Coffers/Payments)
    // owns the page heading. The hub's identity is carried by its tablist
    // aria-label.
    await waitFor(() =>
      expect(screen.getByRole('tablist', { name: /rewards sections/i })).toBeInTheDocument(),
    );
  });
});
