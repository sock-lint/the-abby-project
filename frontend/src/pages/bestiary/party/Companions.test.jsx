import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
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

describe('Companions tab', () => {
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

  it('renders pets and counts each filter pill', async () => {
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: PETS, mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText(/Drake/)).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: /All \(3\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Active \(1\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Hungry \(2\)/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Ready to evolve \(1\)/ })).toBeInTheDocument();
  });

  it('shows a soft whisper line under bored/stale pets and dims their sprite', async () => {
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: PETS, mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText(/Fox/)).toBeInTheDocument());
    expect(screen.getByText(/a little bored/i)).toBeInTheDocument();
    expect(screen.getByText(/getting hungry/i)).toBeInTheDocument();
    // The bored Fox sprite is dimmed; the happy Drake is not. The sprite
    // catalog is empty in tests so RpgSprite emits an emoji fallback span;
    // the data-dim attribute is the same regardless of which branch wins.
    const fox = screen.getByLabelText(/Earth Fox/);
    expect(fox).toHaveAttribute('data-dim', 'bored');
    const drake = screen.getByLabelText(/Fire Drake/);
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
    await waitFor(() => expect(screen.getByText(/Drake/)).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /Hungry/ }));
    await waitFor(() => {
      expect(screen.queryByText(/Drake/)).toBeNull();
      expect(screen.getByText(/Fox/)).toBeInTheDocument();
      expect(screen.getByText(/Wolf/)).toBeInTheDocument();
    });
  });

  it('Ready to evolve filter shows only pets with growth ≥ 90', async () => {
    const user = userEvent.setup();
    renderPage([
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: PETS, mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText(/Drake/)).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /Ready to evolve/ }));
    await waitFor(() => {
      expect(screen.getByText(/Drake/)).toBeInTheDocument();
      expect(screen.queryByText(/Fox/)).toBeNull();
      expect(screen.queryByText(/Wolf/)).toBeNull();
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
    await waitFor(() => expect(screen.getByText(/Drake/)).toBeInTheDocument());
    await user.click(screen.getByText(/Drake/));
    const setActive = await screen.findByRole('button', { name: /set active/i });
    await user.click(setActive);
    await waitFor(() => expect(activate.calls).toHaveLength(1));
    expect(activate.calls[0].url).toMatch(/\/pets\/1\/activate\/$/);
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
    await waitFor(() => expect(screen.getByText(/Drake/)).toBeInTheDocument());
    await user.click(screen.getByText(/Drake/));
    const foodBtn = await screen.findByTitle('Berries');
    await user.click(foodBtn);
    await waitFor(() => expect(feed.calls).toHaveLength(1));
    expect(feed.calls[0].url).toMatch(/\/pets\/1\/feed\/$/);
    expect(feed.calls[0].body).toEqual({ food_item_id: 100 });
  });
});
