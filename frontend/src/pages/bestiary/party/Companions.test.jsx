import { describe, expect, it, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Companions from './Companions.jsx';
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

const PETS = [
  {
    id: 1,
    species: { name: 'Drake', sprite_key: 'drake', icon: '🐉', slug: 'drake' },
    potion: { name: 'Fire', slug: 'fire', rarity: 'rare' },
    growth_points: 95,
    is_active: false,
    evolved_to_mount: false,
    happiness_level: 'happy',
  },
  {
    id: 2,
    species: { name: 'Fox', sprite_key: 'fox', icon: '🦊', slug: 'fox' },
    potion: { name: 'Earth', slug: 'earth', rarity: 'common' },
    growth_points: 30,
    is_active: true,
    evolved_to_mount: false,
    happiness_level: 'bored',
  },
  {
    id: 3,
    species: { name: 'Wolf', sprite_key: 'wolf', icon: '🐺', slug: 'wolf' },
    potion: { name: 'Sky', slug: 'sky', rarity: 'uncommon' },
    growth_points: 50,
    is_active: false,
    evolved_to_mount: false,
    happiness_level: 'stale',
  },
];

const FOOD_INVENTORY = [
  {
    item: { id: 100, item_type: 'food', name: 'Berries', sprite_key: 'berries', icon: '🫐' },
    quantity: 5,
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
        <Companions />
      </AuthProvider>
    </MemoryRouter>,
  );
}

function collection() { return within(screen.getByRole('list', { name: 'Your companions' })); }

describe('Companions tab', () => {
  it('checks incubation before suggesting supplies, and offers recovery when the check fails', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const check = spyHandler('get', '*/api/pets/incubations/', async () => {
      if (check.calls.length === 1) {
        await pending;
        return HttpResponse.json({ detail: 'Egg status unavailable' }, { status: 503 });
      }
      return { incubation: { id: 7, status: 'incubating', is_ready: false, remaining_seconds: 7200 } };
    });
    renderPage([
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], total_possible: 15 })),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      check.handler,
    ]);
    try {
      expect(await screen.findByText('Checking your egg’s progress…')).toBeInTheDocument();
      expect(screen.queryByText(/collect an egg and a potion/i)).toBeNull();
      await act(async () => { release(); await pending; });
      expect(await screen.findByRole('alert')).toHaveTextContent('Egg status unavailable');
      expect(screen.queryByText(/collect an egg and a potion/i)).toBeNull();
      await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }));
      expect(await screen.findByText(/Your egg is incubating/)).toBeInTheDocument();
      expect(check.calls).toHaveLength(2);
      expect(new URL(check.calls[1].url).pathname).toBe('/api/pets/incubations/');
    } finally { await act(async () => { release(); await pending; }); }
  });

  it.each([
    { is_ready: false, status: 'incubating', message: 'Your egg is incubating' },
    { is_ready: true, status: 'ready', message: 'Your egg is ready to hatch' },
  ])('guides a child with a $status egg back to the Hatchery', async ({ is_ready, status, message }) => {
    renderPage([
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], total_possible: 15 })),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      http.get('*/api/pets/incubations/', () => HttpResponse.json({ incubation: {
        id: 7, is_ready, status, remaining_seconds: is_ready ? 0 : 7200,
      } })),
    ]);
    expect(await screen.findByText(new RegExp(message))).toBeInTheDocument();
    expect(screen.queryByText(/collect an egg and a potion|use an available egg and potion/i)).toBeNull();
    expect(screen.getByRole('link', { name: 'Visit the Hatchery' })).toHaveAttribute('href', '/bestiary?tab=hatchery');
  });

  it('shows the server food effect before spending a serving', async () => {
    const user = userEvent.setup();
    const feed = spyHandler('post', /\/api\/pets\/1\/feed\/$/, { new_growth: 100, growth_added: 10, evolved: false });
    renderPage([
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [PETS[0]], mounts: [], total_possible: 48 })),
      http.get('*/api/inventory/', () => HttpResponse.json([{ quantity: 2, item: {
        id: 100, item_type: 'food', name: 'Rare berries', rarity: 'rare', icon: '🫐',
        metadata: { growth: 999 }, effect_summary: 'Adds 10 growth, plus 10 more for a pet that prefers this food.',
      } }])),
      feed.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: /Care for Fire Drake/ }));
    const care = screen.getByRole('dialog', { name: 'Care for Fire Drake' });
    expect(within(care).getByText('Adds 10 growth, plus 10 more for a pet that prefers this food.')).toBeInTheDocument();
    expect(feed.calls).toHaveLength(0);
    await user.click(within(care).getByRole('button', { name: /Rare berries/ }));
    await waitFor(() => expect(feed.calls).toHaveLength(1));
    expect(feed.calls[0]).toMatchObject({ method: 'POST', body: { food_item_id: 100 } });
  });

  it('opens real care from the feed action even when the collection filter excludes it', async () => {
    const user = userEvent.setup();
    const feed = spyHandler('post', /\/api\/pets\/1\/feed\/$/, { new_growth: 100, growth_added: 5, evolved: false });
    renderPage([
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [{ ...PETS[0], is_active: true }, { ...PETS[1], is_active: false }], mounts: [], total_possible: 48 })),
      http.get('*/api/inventory/', () => HttpResponse.json(FOOD_INVENTORY)),
      feed.handler,
    ]);
    await screen.findByRole('button', { name: 'Feed your companion' });
    expect(screen.queryByRole('button', { name: 'Show 3D view' })).toBeNull();
    await user.click(screen.getByRole('tab', { name: /Hungry/ }));
    expect(collection().queryByText(/Drake/)).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Feed your companion' }));
    const care = await screen.findByRole('dialog', { name: 'Care for Fire Drake' });
    expect(feed.calls).toHaveLength(0);
    await user.click(within(care).getByRole('button', { name: /Berries/ }));
    await waitFor(() => expect(feed.calls).toHaveLength(1));
    expect(feed.calls[0]).toMatchObject({ method: 'POST', body: { food_item_id: 100 } });
  });
  it('renders empty state when no pets', async () => {
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/no companions yet/i)).toBeInTheDocument(),
    );
  });

  // "No companions yet. Find eggs and potions in drops…" used to render on a
  // failed fetch too, which reads as an empty party rather than a broken load.
  it('shows a retry-able error instead of the empty state when the stable fetch fails', async () => {
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ detail: 'Stable offline' }, { status: 500 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toMatch(/stable offline/i),
    );
    expect(screen.queryByText(/no companions yet/i)).toBeNull();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('renders pets and counts each filter pill', async () => {
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: PETS, mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(collection().getByText(/Drake/)).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: /All \(3\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Active \(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Hungry \(2\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Almost grown \(1\)/ })).toBeInTheDocument();
  });

  it('wraps each pet sprite with a rarity-keyed atlas halo', async () => {
    const { container } = renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: PETS, mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(collection().getByText(/Drake/)).toBeInTheDocument());
    // Drake (rare) → ring-royal, Fox (common) → ring-moss, Wolf (uncommon) → ring-sheikah-teal
    const haloes = container.querySelectorAll('[class*="ring-royal"], [class*="ring-moss"], [class*="ring-sheikah-teal"]');
    // At minimum the three pets above and the active-pet card outer ring → 3+ matches
    expect(haloes.length).toBeGreaterThanOrEqual(3);
  });

  it('does not dim a pet that has evolved to a mount, even if happiness slipped', async () => {
    // Defensive: an evolved pet's `happiness_level` is always `happy` per
    // ``happiness_for_pet`` in apps/pets/services.py, but if a stale
    // payload ever leaked through, the frontend should still suppress dim
    // for evolved rows so the parent doesn't see a sad mount on the
    // stable wall.
    const stalePet = {
      id: 99,
      species: { name: 'Drake', sprite_key: 'drake', icon: '🐉', slug: 'drake' },
      potion: { name: 'Fire', slug: 'fire', rarity: 'rare' },
      growth_points: 100,
      is_active: false,
      evolved_to_mount: true,
      happiness_level: 'stale', // intentionally inconsistent for this regression test
    };
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [stalePet], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(collection().getByText(/Drake/)).toBeInTheDocument());
    const drake = collection().getByRole('img', { name: /Fire Drake/ });
    expect(drake).not.toHaveAttribute('data-dim');
    // The whisper copy is also suppressed for evolved pets.
    expect(screen.queryByText(/getting hungry/i)).toBeNull();
  });

  it('shows a soft whisper line under bored/stale pets and dims their sprite', async () => {
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: PETS, mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(collection().getByText(/Fox/)).toBeInTheDocument());
    expect(screen.getByText(/a little bored/i)).toBeInTheDocument();
    expect(screen.getByText(/getting hungry/i)).toBeInTheDocument();
    // The bored Fox sprite is dimmed; the happy Drake is not. The sprite
    // catalog is empty in tests so RpgSprite emits an emoji fallback span;
    // the data-dim attribute is the same regardless of which branch wins.
    const fox = collection().getByRole('img', { name: /Earth Fox/ });
    expect(fox).toHaveAttribute('data-dim', 'bored');
    const drake = collection().getByRole('img', { name: /Fire Drake/ });
    expect(drake).not.toHaveAttribute('data-dim');
  });

  it('Hungry filter shows only bored/stale/away pets', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: PETS, mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(collection().getByText(/Drake/)).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /Hungry/ }));
    await waitFor(() => {
      expect(collection().queryByText(/Drake/)).toBeNull();
      expect(collection().getByText(/Fox/)).toBeInTheDocument();
      expect(collection().getByText(/Wolf/)).toBeInTheDocument();
    });
  });

  it('Almost grown filter shows only pets with growth ≥ 90', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: PETS, mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(collection().getByText(/Drake/)).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /Almost grown/ }));
    await waitFor(() => {
      expect(collection().getByText(/Drake/)).toBeInTheDocument();
      expect(collection().queryByText(/Fox/)).toBeNull();
      expect(collection().queryByText(/Wolf/)).toBeNull();
    });
  });

  it('clicking a pet then Set active POSTs to activate endpoint', async () => {
    const user = userEvent.setup();
    const activate = spyHandler('post', /\/api\/pets\/\d+\/activate\/$/, { ok: true });
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [PETS[0]], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      activate.handler,
    ]);
    await waitFor(() => expect(collection().getByText(/Drake/)).toBeInTheDocument());
    await user.click(collection().getByText(/Drake/));
    const setActive = await screen.findByRole('button', { name: /set active/i });
    await user.click(setActive);
    await waitFor(() => expect(activate.calls).toHaveLength(1));
    expect(activate.calls[0].url).toMatch(/\/pets\/1\/activate\/$/);
  });

  it('opens and closes companion care from the keyboard without nesting action buttons', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [PETS[0]], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json(FOOD_INVENTORY)),
    ]);
    const care = await screen.findByRole('button', { name: 'Care for Fire Drake' });
    expect(care).toHaveAttribute('aria-expanded', 'false');
    care.focus();
    await user.keyboard('{Enter}');
    expect(care).toHaveAttribute('aria-expanded', 'true');
    const activate = screen.getByRole('button', { name: /set active/i });
    const food = screen.getByTitle('Berries');
    expect(care).not.toContainElement(activate);
    expect(care).not.toContainElement(food);
    await user.keyboard('{Escape}');
    expect(care).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('button', { name: /set active/i })).toBeNull();
  });

  it('clicking a food chip POSTs to feed endpoint with the food item id', async () => {
    const user = userEvent.setup();
    const feed = spyHandler('post', /\/api\/pets\/\d+\/feed\/$/, { ok: true });
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [PETS[0]], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json(FOOD_INVENTORY)),
      feed.handler,
    ]);
    await waitFor(() => expect(collection().getByText(/Drake/)).toBeInTheDocument());
    await user.click(collection().getByText(/Drake/));
    const foodBtn = await screen.findByTitle('Berries');
    await user.click(foodBtn);
    await waitFor(() => expect(feed.calls).toHaveLength(1));
    expect(feed.calls[0].url).toMatch(/\/pets\/1\/feed\/$/);
    expect(feed.calls[0].body).toEqual({ food_item_id: 100 });
  });

  // Feeding consumes the item on one tap, and the name used to live only in
  // `title` — which never surfaces on touch, the app's primary device class.
  it('prints the food name on the chip face, not just in a hover title', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [PETS[0]], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json(FOOD_INVENTORY)),
    ]);
    await waitFor(() => expect(collection().getByText(/Drake/)).toBeInTheDocument());
    await user.click(collection().getByText(/Drake/));
    const chip = await screen.findByTitle('Berries');
    expect(within(chip).getByText('Berries')).toBeInTheDocument();
    expect(within(chip).getByText('×5')).toBeInTheDocument();
  });
});
