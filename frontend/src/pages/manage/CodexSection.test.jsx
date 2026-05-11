import { describe, expect, it, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CodexSection from './CodexSection.jsx';
import { server } from '../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

const ACTIVE_SECTION_KEY = 'manage:codex:active-section';

beforeEach(() => {
  // The active-section key is sticky via localStorage; clear it so each
  // case starts on the default Items spine unless it pre-seeds otherwise.
  window.localStorage.removeItem(ACTIVE_SECTION_KEY);
});

describe('CodexSection', () => {
  it('renders with empty catalogs', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    render(<CodexSection />);
    // The five-spine shelf renders even with empty catalogs; assert the
    // shelf is the navigation surface.
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /Items/ })).toBeInTheDocument(),
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

  it('renders all five codex-book spines on the shelf', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
      http.get('*/api/quests/catalog/', () => HttpResponse.json([])),
    );
    render(<CodexSection />);
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /Items/ })).toBeInTheDocument(),
    );
    for (const label of ['Items', 'Creatures', 'Mounts', 'Adventures', 'Sprites']) {
      expect(screen.getByRole('tab', { name: new RegExp(label) })).toBeInTheDocument();
    }
  });

  it('clicking the Sprites spine swaps in the sprites grid', async () => {
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
    const user = userEvent.setup();
    render(<CodexSection />);

    // Wait for the shelf to render, then activate the Sprites spine.
    const spritesSpine = await screen.findByRole('tab', { name: /Sprites/ });
    await user.click(spritesSpine);

    // Only after the spine is selected does the sprite slug appear.
    await waitFor(() => expect(screen.getByText('fox-idle')).toBeInTheDocument());
  });

  it('restores the previously-active section from localStorage on mount', async () => {
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.get('*/api/pets/species/catalog/', () => HttpResponse.json([])),
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
    window.localStorage.setItem(ACTIVE_SECTION_KEY, 'sprites');

    render(<CodexSection />);

    // Without clicking anything, the Sprites section's contents render
    // because the persisted active-section was restored.
    await waitFor(() => expect(screen.getByText('fox-idle')).toBeInTheDocument());
  });
});
