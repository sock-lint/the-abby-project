import { describe, expect, it, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Mounts from './Mounts.jsx';
import { AuthProvider } from '../../../hooks/useApi.js';
import { server } from '../../../test/server.js';
import { spyHandler } from '../../../test/spy.js';
import { buildUser } from '../../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

beforeEach(() => {
  // TomeShelf's activeId effect calls scrollIntoView; stub for jsdom.
  Element.prototype.scrollIntoView = vi.fn();
});

const RECENT_BRED = new Date(Date.now() - 1000).toISOString();

const MOUNTS = [
  {
    id: 9,
    species: { name: 'Griffon', sprite_key: 'griffon', icon: '🦅' },
    potion: { name: 'Sky', slug: 'sky', rarity: 'rare' },
    is_active: true,
    last_bred_at: null,
  },
  {
    id: 10,
    species: { name: 'Wolf', sprite_key: 'wolf', icon: '🐺' },
    potion: { name: 'Earth', slug: 'earth', rarity: 'common' },
    is_active: false,
    last_bred_at: RECENT_BRED,
  },
];

function renderPage(handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Mounts />
      </AuthProvider>
    </MemoryRouter>,
  );
}

function collection() { return within(screen.getByRole('list', { name: 'Your mounts' })); }

describe('Mounts tab', () => {
  it('lets the waiting mount begin an expedition directly from its home', async () => {
    const user = userEvent.setup();
    const start = spyHandler('post', /\/api\/mounts\/9\/expedition\/$/, { id: 99, status: 'active', tier: 'short' });
    renderPage([
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [MOUNTS[0]], total_possible: 48 })),
      start.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: 'Explore with Griffon' }));
    expect(start.calls).toHaveLength(0);
    await user.click(await screen.findByRole('button', { name: /Short expedition/ }));
    await waitFor(() => expect(start.calls).toHaveLength(1));
    expect(start.calls[0]).toMatchObject({ method: 'POST', body: { tier: 'short' } });
  });
  it('renders empty state when no mounts', async () => {
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [], total_possible: 48 }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/no mounts yet/i)).toBeInTheDocument());
  });

  it('shows a stable load error and retries without claiming the collection is empty', async () => {
    const user = userEvent.setup();
    let requests = 0;
    renderPage([
      http.get('*/api/pets/stable/', () => {
        requests += 1;
        return requests === 1
          ? HttpResponse.json({ detail: 'Stable offline' }, { status: 500 })
          : HttpResponse.json({ pets: [], mounts: [MOUNTS[0]], total_possible: 48 });
      }),
    ]);
    expect(await screen.findByRole('alert')).toHaveTextContent('Stable offline');
    expect(screen.queryByText(/no mounts yet/i)).toBeNull();
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByRole('button', { name: 'Visit Sky Griffon' })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(requests).toBe(2);
  });

  it('renders mounts and counts each filter pill', async () => {
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: MOUNTS, total_possible: 48 }),
      ),
    ]);
    await waitFor(() => expect(collection().getByText(/Griffon/)).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: /All \(2\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Active \(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Ready to breed \(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /On cooldown \(1\)/ })).toBeInTheDocument();
  });

  it('Ready to breed filter shows only mounts off cooldown', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: MOUNTS, total_possible: 48 }),
      ),
    ]);
    await waitFor(() => expect(collection().getByText(/Griffon/)).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /Ready to breed/ }));
    await waitFor(() => {
      expect(collection().getByText(/Griffon/)).toBeInTheDocument();
      expect(collection().queryByText(/Wolf/)).toBeNull();
    });
  });

  it('On cooldown filter shows only mounts within breeding window', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: MOUNTS, total_possible: 48 }),
      ),
    ]);
    await waitFor(() => expect(collection().getByText(/Griffon/)).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /On cooldown/ }));
    await waitFor(() => {
      expect(collection().queryByText(/Griffon/)).toBeNull();
      expect(collection().getByText(/Wolf/)).toBeInTheDocument();
    });
  });

  it('Set active POSTs to mount activate endpoint', async () => {
    const user = userEvent.setup();
    const activate = spyHandler('post', /\/api\/mounts\/\d+\/activate\/$/, { ok: true });
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [MOUNTS[1]], total_possible: 48 }),
      ),
      activate.handler,
    ]);
    await waitFor(() => expect(collection().getByText(/Wolf/)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /set active/i }));
    await waitFor(() => expect(activate.calls).toHaveLength(1));
    expect(activate.calls[0].url).toMatch(/\/mounts\/10\/activate\/$/);
  });

  it('Expedition button opens the launch sheet and POSTs the tier', async () => {
    const user = userEvent.setup();
    const start = spyHandler(
      'post',
      /\/api\/mounts\/\d+\/expedition\/$/,
      { id: 99, status: 'active', tier: 'short' },
    );
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [MOUNTS[1]], total_possible: 48 }),
      ),
      start.handler,
    ]);
    await waitFor(() => expect(collection().getByText(/Wolf/)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /Send Wolf on an expedition/i }));
    // Sheet appears and offers three tier choices.
    const shortTierBtn = await screen.findByRole('button', { name: /short expedition/i });
    await user.click(shortTierBtn);
    await waitFor(() => expect(start.calls).toHaveLength(1));
    expect(start.calls[0].url).toMatch(/\/mounts\/10\/expedition\/$/);
    expect(start.calls[0].body).toEqual({ tier: 'short' });
  });

  it('shows the out-on-expedition state for a mount that is still exploring', async () => {
    const futureReturn = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    const mountOut = {
      ...MOUNTS[0],
      active_expedition: {
        id: 21,
        status: 'active',
        tier: 'short',
        is_ready: false,
        seconds_remaining: 1800,
        returns_at: futureReturn,
      },
    };
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [mountOut], total_possible: 48 }),
      ),
    ]);
    // Wait for the "exploring · 30m" countdown chip on the mount card.
    await waitFor(() =>
      expect(collection().getByText(/exploring · 30m/i)).toBeInTheDocument(),
    );
    expect(screen.queryByRole('button', { name: /Send Griffon on an expedition/i })).toBeNull();
    expect(screen.getByRole('tab', { name: /Out exploring \(1\)/ })).toBeInTheDocument();
  });

  it('exports the server-confirmed expedition return time to Google Calendar', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/pets/stable/', () => HttpResponse.json({
        pets: [], total_possible: 48,
        mounts: [{ ...MOUNTS[0], active_expedition: {
          id: 21, status: 'active', is_ready: false, seconds_remaining: 1800,
          returns_at: '2026-10-11T15:30:00-07:00',
        } }],
      })),
    ]);
    await user.click(await screen.findByRole('button', { name: /add .*expedition return.*to calendar/i }));
    const url = new URL(screen.getByRole('link', { name: /Google Calendar/i }).href);
    expect(url.searchParams.get('text')).toBe('Expedition return: Sky Griffon');
    expect(url.searchParams.get('dates')).toBe('20261011T223000Z/20261011T230000Z');
    expect(url.searchParams.get('details')).toContain('/bestiary?tab=mounts');
  });

  it('Claim rewards button POSTs to the claim endpoint when the expedition is ready', async () => {
    const user = userEvent.setup();
    const mountReady = {
      ...MOUNTS[0],
      active_expedition: {
        id: 33,
        status: 'active',
        tier: 'standard',
        is_ready: true,
        seconds_remaining: 0,
        returns_at: new Date(Date.now() - 1000).toISOString(),
      },
    };
    const claim = spyHandler(
      'post',
      /\/api\/expeditions\/\d+\/claim\/$/,
      {
        expedition_id: 33,
        tier: 'standard',
        coins_awarded: 30,
        items: [],
        freshly_claimed: true,
        mount: { id: mountReady.id, species_name: 'Griffon', species_sprite_key: 'griffon', species_icon: '🦅', potion_name: 'Sky', potion_slug: 'sky' },
      },
    );
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [mountReady], total_possible: 48 }),
      ),
      claim.handler,
    ]);
    await waitFor(() => expect(collection().getByText(/Griffon/)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /claim expedition rewards/i }));
    await waitFor(() => expect(claim.calls).toHaveLength(1));
    expect(claim.calls[0].url).toMatch(/\/expeditions\/33\/claim\/$/);
    // Lock the request body contract — claim takes no body today,
    // so any future drift surfaces here instead of silently shipping.
    expect(claim.calls[0].body).toBeNull();
  });
});
