import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildUser } from '../../test/factories.js';
import { spyHandler } from '../../test/spy.js';
import MockPulse from '../../test/pulse.jsx';
import { emptyPulse } from '../../test/pulseFixtures.js';
import FirstEncounterSheet from './FirstEncounterSheet.jsx';

localStorage.setItem('abby_auth_token', 'test-token');

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

// Tiny probe that surfaces the current location into the DOM so the test can
// assert on the post-navigate URL without coupling to a real page component.
function LocationProbe() {
  const location = useLocation();
  return <div data-testid="probe-url">{location.pathname + location.search}</div>;
}

// Newly-unlocked slugs ride the shared heartbeat now (the hook used to
// re-fetch the entire dashboard every 20s just to read them).
function renderSheet(slugs = []) {
  return render(
    <MockPulse pulse={emptyPulse({ newly_unlocked_lorebook: slugs })}>
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <Routes>
            <Route
              path="*"
              element={
                <>
                  <FirstEncounterSheet />
                  <LocationProbe />
                </>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </MockPulse>,
  );
}

const baseHandlers = (entry) => [
  http.get('*/api/auth/me/', () =>
    HttpResponse.json(buildUser({ role: 'child', lorebook_flags: {} })),
  ),
  http.get('*/api/dashboard/', () =>
    HttpResponse.json({ newly_unlocked_lorebook: [entry.slug] }),
  ),
  http.get('*/api/lorebook/', () =>
    HttpResponse.json({
      counts: { unlocked: 1, trained: 0, total: 1 },
      entries: [entry],
    }),
  ),
];

const petsEntry = {
  slug: 'pets',
  title: 'Pets',
  icon: '🐾',
  audience_title: 'The stable hatchery',
  summary: 'Egg + potion companions.',
  kid_voice: 'Pets are companions found along the road.',
  mechanics: [],
  economy: {},
  trial_template: 'sequence',
  trial: {
    prompt: 'Hatch, feed, evolve',
    payoff: 'Egg → Pet → Mount',
    steps: ['x', 'y', 'z'],
  },
  unlocked: true,
  trained: false,
};

describe('FirstEncounterSheet', () => {
  it('shows the new copy and dismisses without navigation when Later is tapped', async () => {
    server.use(...baseHandlers(petsEntry));
    const patch = spyHandler('patch', /\/api\/auth\/me\/$/, () =>
      HttpResponse.json(buildUser({ role: 'child', lorebook_flags: { pets_seen: true } })),
    );
    server.use(patch.handler);

    const user = userEvent.setup();
    renderSheet([petsEntry.slug]);

    expect(
      await screen.findByRole('dialog', { name: /a new page is open/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /pets/i })).toBeInTheDocument();
    expect(
      screen.getByText(/a new training awaits you in your lorebook/i),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /^later$/i }));
    await waitFor(() => expect(patch.calls).toHaveLength(1));
    expect(patch.calls[0].body).toEqual({ lorebook_flags: { pets_seen: true } });
    // Stays on the same path, no trial query param appended.
    expect(screen.getByTestId('probe-url').textContent).toBe('/');
  });

  it('navigates to the lorebook trial deep-link when Take me there is tapped', async () => {
    server.use(...baseHandlers(petsEntry));
    const patch = spyHandler('patch', /\/api\/auth\/me\/$/, () =>
      HttpResponse.json(buildUser({ role: 'child', lorebook_flags: { pets_seen: true } })),
    );
    server.use(patch.handler);

    const user = userEvent.setup();
    renderSheet([petsEntry.slug]);

    expect(
      await screen.findByRole('dialog', { name: /a new page is open/i }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /take me there/i }));

    await waitFor(() => expect(patch.calls).toHaveLength(1));
    await waitFor(() =>
      expect(screen.getByTestId('probe-url').textContent).toBe(
        '/atlas?tab=lorebook&trial=pets',
      ),
    );
  });

  // The unlock rides the 30s heartbeat, which can land while a kid is typing
  // in another sheet. Opening on top of it would steal focus and dismiss the
  // phone keyboard mid-word, so the entry waits until the screen is clear.
  it('waits for an already-open dialog to close before showing', async () => {
    server.use(...baseHandlers(petsEntry));
    const openForm = document.createElement('div');
    openForm.setAttribute('role', 'dialog');
    document.body.appendChild(openForm);

    renderSheet([petsEntry.slug]);

    await act(async () => { await new Promise((r) => setTimeout(r, 60)); });
    expect(
      screen.queryByRole('dialog', { name: /a new page is open/i }),
    ).toBeNull();

    await act(async () => { openForm.remove(); });
    expect(
      await screen.findByRole('dialog', { name: /a new page is open/i }),
    ).toBeInTheDocument();
  });
});
