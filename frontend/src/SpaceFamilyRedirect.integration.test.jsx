import { afterEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { AuthProvider } from './hooks/useApi';
import { server } from './test/server';
import { buildParent } from './test/factories';

vi.mock('framer-motion', async () => ({
  ...await vi.importActual('framer-motion'), AnimatePresence: ({ children }) => children,
}));

afterEach(() => { window.history.replaceState({}, '', '/'); });

function renderPersonalParent(destination) {
  const parent = buildParent({ id: 90, family: { id: 1 } });
    sessionStorage.setItem('abby:spaces:1:90', JSON.stringify({
      space: 'personal', personal: '/bestiary?tab=mounts', family: '/',
    }));
    window.history.replaceState({}, '', destination);
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(parent)),
      http.get('*/api/notifications/pending-celebration/', () => HttpResponse.json(null)),
      http.get('*/api/children/', () => HttpResponse.json([{ id: 7, display_name: 'Abby' }])),
      http.get('*/api/children/7/overview/', () => HttpResponse.json({
        child: { id: 7, display_name: 'Abby' }, level: 1, coin_balance: 0,
        skills: [], badges: [], pets: [], mounts: [],
      })));
    const user = userEvent.setup();
    render(<AuthProvider><App /></AuthProvider>);
    return user;
}

describe('Family-only destination integration', () => {
  it.each(['/family?child=7', '/manage', '/Manage', '/Family?child=7', '/%66amily?child=7', '/ACTIVITY'])(
    'returns to the previous personal page after reloading a Family-only link: %s', async (destination) => {
    const user = renderPersonalParent(destination);
    await screen.findByRole('button', { name: /^Family/ });
    await waitFor(() => expect(screen.getByRole('button', { name: /^Family/ })).toHaveAttribute('aria-pressed', 'true'));
    await user.click(screen.getByRole('button', { name: 'My space' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'My space' })).toHaveAttribute('aria-pressed', 'true'));
    expect(window.location.pathname + window.location.search).toBe('/bestiary?tab=mounts');
  });

  it('returns to personal Pets after opening Manage from My space', async () => {
    const user = renderPersonalParent('/bestiary?tab=mounts');
    await screen.findByRole('button', { name: 'My space' });
    await waitFor(() => expect(screen.getByRole('button', { name: 'My space' })).toHaveAttribute('aria-pressed', 'true'));
    await user.click(screen.getByRole('link', { name: 'Manage' }));
    await waitFor(() => expect(screen.getByRole('button', { name: /^Family/ })).toHaveAttribute('aria-pressed', 'true'));
    await user.click(screen.getByRole('button', { name: 'My space' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'My space' })).toHaveAttribute('aria-pressed', 'true'));
    expect(window.location.pathname + window.location.search).toBe('/bestiary?tab=mounts');
  });
});
