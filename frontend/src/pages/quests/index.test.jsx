import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import QuestsHub from './index.jsx';
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

describe('QuestsHub', () => {
  it.each(['/quests', '/quests?tab=study&child=7'])(
    'keeps a parent’s personal Tasks on Habits without Homework: %s', async (route) => {
      sessionStorage.setItem('abby:spaces:1:90', JSON.stringify({ space: 'personal' }));
      const reads = [];
      server.use(
        http.get('*/api/auth/me/', () => HttpResponse.json(buildParent({ id: 90, family: { id: 1 } }))),
        http.get('*/api/habits/', ({ request }) => {
          reads.push({ space: request.headers.get('X-Abby-Space'), userId: new URL(request.url).searchParams.get('user_id') });
          return HttpResponse.json([]);
        }),
      );
      render(<MemoryRouter initialEntries={[route]}><AuthProvider><SpaceProvider><QuestsHub /><AccountIdentity /></SpaceProvider></AuthProvider></MemoryRouter>);
      await waitFor(() => expect(screen.getByRole('status', { name: 'Account identity' })).toHaveTextContent('90:parent'));
      expect(screen.getByRole('tab', { name: 'Habits' })).toHaveAttribute('aria-selected', 'true');
      expect(screen.queryByRole('tab', { name: 'Homework' })).not.toBeInTheDocument();
      expect(screen.getAllByRole('tab')).toHaveLength(6);
      await waitFor(() => expect(reads).toContainEqual({ space: 'personal', userId: null }));
      expect(screen.queryByRole('combobox', { name: 'Child' })).not.toBeInTheDocument();
    },
  );

  it.each(['family', 'child'])('keeps Homework as the default for %s Tasks', async (viewer) => {
    const account = viewer === 'family' ? buildParent({ id: 90, family: { id: 1 } }) : buildUser({ id: 7, family: { id: 1 } });
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(account)),
      http.get('*/api/children/', () => HttpResponse.json([buildUser({ id: 7 })])));
    render(<MemoryRouter initialEntries={['/quests']}><AuthProvider><SpaceProvider><QuestsHub /><AccountIdentity /></SpaceProvider></AuthProvider></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole('status', { name: 'Account identity' })).toHaveTextContent(`${account.id}:${account.role}`));
    expect(screen.getByRole('tab', { name: 'Homework' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByRole('tab')).toHaveLength(7);
  });
  it('opens optional Challenges from Tasks and explains how they fit everyday work', async () => {
    const user = userEvent.setup();
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
    render(
      <MemoryRouter>
        <AuthProvider>
          <QuestsHub />
        </AuthProvider>
      </MemoryRouter>,
    );
    await user.click(await screen.findByRole('tab', { name: 'Challenges' }));
    const overview = await screen.findByRole('region', { name: 'Challenges overview' });
    expect(overview.querySelector('[data-folio-verso="true"]')).not.toBeNull();
    expect(overview.querySelector('[data-folio-recto="true"]')).not.toBeNull();
    expect(screen.getByRole('tab', { name: 'Challenges' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('All matching challenges keep progressing in the background. Pinning simply keeps one on Today.')).toBeInTheDocument();
  });

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

  it('keeps activities in Tasks while printing lives in Rewards', async () => {
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
    expect(screen.getByRole('tab', { name: /reading/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /challenges/i })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: /3d print/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole('tab')).toHaveLength(7);
  });

  it('opens the bookshelf from the Reading tab', async () => {
    const user = userEvent.setup();
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
    render(<MemoryRouter><AuthProvider><QuestsHub /></AuthProvider></MemoryRouter>);
    await user.click(await screen.findByRole('tab', { name: 'Reading', exact: true }));
    expect(await screen.findByRole('heading', { name: 'Your bookshelf', exact: true })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Reading', exact: true })).toHaveAttribute('aria-selected', 'true');
  });

  it.each([
    ['/quests?tab=forge', '/treasury?tab=forge'],
    ['/quests?tab=forge&new=1&token=private#secret', '/treasury?tab=forge&new=1'],
    ['/quests?tab=forge&new=0', '/treasury?tab=forge'],
  ])('moves old printing links safely: %s', async (from, expected) => {
    function Destination() {
      const location = useLocation();
      return <p>{location.pathname}{location.search}{location.hash}</p>;
    }
    render(<MemoryRouter initialEntries={[from]}><Routes>
      <Route path="/quests" element={<QuestsHub />} />
      <Route path="/treasury" element={<Destination />} />
    </Routes></MemoryRouter>);
    expect(await screen.findByText(expected)).toBeInTheDocument();
  });
});
