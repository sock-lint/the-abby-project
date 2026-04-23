import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import CodexSection from './CodexSection.jsx';
import { server } from '../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('CodexSection', () => {
  it('renders with empty catalogs', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    render(<CodexSection />);
    // Empty catalogs render an empty state message; the render just needs to
    // settle past the loader.
    await waitFor(() =>
      expect(screen.getAllByText((t) => /codex|empty|no|content|pet|item|quest/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('renders with a populated item catalog', async () => {
    server.use(
      http.get('*/api/items/catalog/', () =>
        HttpResponse.json([
          { slug: 'gold-coin', name: 'Gold Coin', item_type: 'coin_pouch', rarity: 'common', icon: '🪙', sprite_key: 'gold-coin-stack', description: 'Shiny' },
        ]),
      ),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    render(<CodexSection />);
    await waitFor(() => expect(screen.getByText(/gold coin/i)).toBeInTheDocument());
  });

  it('renders Mounts and Sprites sections', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () =>
        HttpResponse.json([
          { id: 1, name: 'Fox', sprite_key: 'fox', icon: '🦊', available_potions: [] },
        ]),
      ),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
      http.get('*/api/sprites/admin/', () =>
        HttpResponse.json([
          {
            slug: 'fox-idle', pack: 'ai-generated', frame_count: 1, fps: 0,
            frame_width_px: 64, frame_height_px: 64,
            prompt: 'a fox', motion: 'idle', style_hint: '', tile_size: 64,
            reference_image_url: '', created_by_name: '',
          },
        ]),
      ),
    );
    render(<CodexSection />);
    await waitFor(() => expect(screen.getByText('Mounts')).toBeInTheDocument());
    expect(screen.getByText('Sprites')).toBeInTheDocument();
    // The sprite admin row surfaces its slug — proves both the admin fetch
    // fired and the SpritesBlock rendered it into the DOM.
    await waitFor(() => expect(screen.getByText('fox-idle')).toBeInTheDocument());
  });
});
