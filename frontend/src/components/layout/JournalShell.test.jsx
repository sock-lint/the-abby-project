import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import JournalShell from './JournalShell.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildUser } from '../../test/factories.js';
import { STORAGE_KEYS } from '../../constants/storage.js';

function renderShell({ route = '/', element }) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <Routes>
          <Route element={<JournalShell />}>
            <Route path="/" element={element || <div>home</div>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('JournalShell', () => {
  it('renders nav + outlet content', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    );
    renderShell({ element: <div>page-body</div> });
    await waitFor(() => expect(screen.getByText('page-body')).toBeInTheDocument());
    // Chapter sidebar labels are rendered regardless of auth state.
    expect(screen.getAllByText('Today').length).toBeGreaterThan(0);
    // No offline banner on a live-auth boot.
    expect(screen.queryByText(/offline — showing your last journal/i)).toBeNull();
  });

  it('hydrates from the cached user and shows the offline banner when boot getMe network-errors', async () => {
    const cached = buildUser({ display_name: 'Cached Abby' });
    localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, 'tok-123');
    localStorage.setItem(STORAGE_KEYS.CACHED_USER, JSON.stringify(cached));
    // HttpResponse.error() rejects the fetch itself (no .status on the
    // thrown error) — the flaky-wifi shape, not an HTTP 401.
    server.use(http.get('*/api/auth/me/', () => HttpResponse.error()));

    renderShell({ element: <div>page-body</div> });

    const banner = await screen.findByText('Offline — showing your last journal');
    expect(banner).toHaveAttribute('role', 'status');
    // The shell rendered the cached identity (AvatarMenu shows the cached
    // display name), proving the session hydrated instead of logging out.
    await waitFor(() =>
      expect(screen.getAllByText('Cached Abby').length).toBeGreaterThan(0),
    );
  });
});
