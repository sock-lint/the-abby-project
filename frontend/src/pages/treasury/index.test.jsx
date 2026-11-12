import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import TreasuryHub from './index.jsx';
import { AuthProvider, useAuth } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildParent, buildUser } from '../../test/factories.js';
import userEvent from '@testing-library/user-event';
import SpaceProvider from '../../providers/SpaceProvider';

function AccountIdentity() {
  const { user } = useAuth();
  return <output aria-label="Account identity">{user?.id}:{user?.role}</output>;
}

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('TreasuryHub', () => {
  it('keeps family rewards focused on shop, print decisions and family money', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
    render(<MemoryRouter><AuthProvider><TreasuryHub /><AccountIdentity /></AuthProvider></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('status', { name: 'Account identity' })).toHaveTextContent('99:parent'));
    expect(screen.getByText('Manage family payments, timecards, rewards, and 3D prints')).toBeInTheDocument();
    expect(screen.queryByText('Track earnings, spend coins, and set savings goals')).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Inventory' })).toBeNull();
    expect(screen.getByRole('tab', { name: 'Payments' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Timecards' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Shop' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '3D Prints' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Savings goals' })).toBeNull();
  });

  it.each(['/treasury', '/treasury?tab=forge', '/treasury?tab=coffers'])(
    'keeps My space Rewards on personal destinations despite a family bookmark: %s', async (route) => {
      sessionStorage.setItem('abby:spaces:1:90', JSON.stringify({ space: 'personal' }));
      const reads = [];
      server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent({ id: 90, family: { id: 1 } }))),
        http.get('*/api/coins/', ({ request }) => {
          reads.push({ space: request.headers.get('X-Abby-Space'), userId: new URL(request.url).searchParams.get('user_id') });
          return HttpResponse.json({ balance: 0, breakdown: {}, recent_transactions: [] });
        }));
      render(<MemoryRouter initialEntries={[route]}><AuthProvider><SpaceProvider><TreasuryHub /><AccountIdentity /></SpaceProvider></AuthProvider></MemoryRouter>);
      await waitFor(() => expect(screen.getByRole('status', { name: 'Account identity' })).toHaveTextContent('90:parent'));
      expect(screen.getByRole('tab', { name: 'Shop' })).toHaveAttribute('aria-selected', 'true');
      expect(screen.getByText('Spend your coins and manage your collection')).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'Inventory' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'Savings goals' })).toBeInTheDocument();
      for (const name of ['Payments', 'Timecards', '3D Prints']) expect(screen.queryByRole('tab', { name })).not.toBeInTheDocument();
      expect(screen.getAllByRole('tab')).toHaveLength(3);
      await waitFor(() => expect(reads).toContainEqual({ space: 'personal', userId: null }));
    },
  );

  it('opens print requests alongside the reward shop', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={['/treasury?tab=bazaar']}>
      <AuthProvider><TreasuryHub /></AuthProvider>
    </MemoryRouter>);
    await user.click(await screen.findByRole('tab', { name: '3D Prints' }));
    expect(screen.getAllByRole('tab')).toHaveLength(6);
    expect(screen.getByText('Track earnings, spend coins, and set savings goals')).toBeInTheDocument();
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
