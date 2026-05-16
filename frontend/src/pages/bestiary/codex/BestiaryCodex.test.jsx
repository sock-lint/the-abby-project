import { describe, expect, it, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import BestiaryCodex from './BestiaryCodex.jsx';
import { server } from '../../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderCodex() {
  return render(
    <MemoryRouter>
      <BestiaryCodex />
    </MemoryRouter>,
  );
}

const samplePotions = [
  { id: 1, slug: 'base', name: 'Base', color_hex: '#aaa', rarity: 'common' },
  { id: 2, slug: 'fire', name: 'Fire', color_hex: '#f00', rarity: 'uncommon' },
];

beforeEach(() => {
  // jsdom doesn't implement scrollIntoView; stub so TomeShelf's effect
  // doesn't throw when activeId changes.
  Element.prototype.scrollIntoView = vi.fn();
  try { window.localStorage.clear(); } catch { /* ignore */ }
});

describe('BestiaryCodex', () => {
  it('renders silhouette tiles for un-discovered species', async () => {
    server.use(
      http.get('*/api/pets/codex/', () =>
        HttpResponse.json({
          species: [
            {
              id: 1, slug: 'dragon', name: 'Dragon', icon: '🐉', sprite_key: 'dragon',
              description: 'Ancient flying lizard.', food_preference: 'meat',
              available_potions: samplePotions,
              discovered: false, owned_pet_ids: [], owned_mount_potion_ids: [],
            },
          ],
          potions: samplePotions,
          totals: { species: 1, discovered_species: 0, mounts_possible: 2, mounts_owned: 0 },
        }),
      ),
    );
    renderCodex();
    await waitFor(() =>
      expect(screen.getByLabelText(/unknown species/i)).toBeInTheDocument(),
    );
    // IncipitBand meta now carries the discovered/total summary in a folio-
    // friendly shape — was a bespoke RuneBadge before the Atlas alignment.
    expect(screen.getByText(/0 of 1/)).toBeInTheDocument();
  });

  it('opens the detail sheet with the evolution row when a discovered tile is tapped', async () => {
    server.use(
      http.get('*/api/pets/codex/', () =>
        HttpResponse.json({
          species: [
            {
              id: 1, slug: 'dragon', name: 'Dragon', icon: '🐉', sprite_key: 'dragon',
              description: 'Ancient flying lizard. Loves stew.', food_preference: 'meat',
              available_potions: samplePotions,
              discovered: true, owned_pet_ids: [12],
              owned_mount_potion_ids: [2],
            },
          ],
          potions: samplePotions,
          totals: { species: 1, discovered_species: 1, mounts_possible: 2, mounts_owned: 1 },
        }),
      ),
    );
    renderCodex();
    const tile = await screen.findByRole('button', { name: /^Dragon/i });
    const user = userEvent.setup();
    await user.click(tile);
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: /dragon/i })).toBeInTheDocument(),
    );
    expect(screen.getByLabelText(/fire dragon — owned/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/base dragon — not yet evolved/i)).toBeInTheDocument();
  });

  it('renders a chapter shelf and switches the active folio on click', async () => {
    server.use(
      http.get('*/api/pets/codex/', () =>
        HttpResponse.json({
          species: [
            // One bonded species (mount owned, not all variants).
            {
              id: 1, slug: 'dragon', name: 'Dragon', icon: '🐉', sprite_key: 'dragon',
              description: 'Bonded one.', available_potions: samplePotions,
              discovered: true, owned_pet_ids: [12], owned_mount_potion_ids: [1],
            },
            // One hatched species (pet only).
            {
              id: 2, slug: 'fox', name: 'Fox', icon: '🦊', sprite_key: 'fox',
              description: 'Hatched but not evolved.', available_potions: samplePotions,
              discovered: true, owned_pet_ids: [22], owned_mount_potion_ids: [],
            },
            // One silhouette.
            {
              id: 3, slug: 'wolf', name: 'Wolf', icon: '🐺', sprite_key: 'wolf',
              description: 'Unseen.', available_potions: samplePotions,
              discovered: false, owned_pet_ids: [], owned_mount_potion_ids: [],
            },
          ],
          potions: samplePotions,
          totals: { species: 3, discovered_species: 2, mounts_possible: 6, mounts_owned: 1 },
        }),
      ),
    );
    renderCodex();

    // Bonded chapter is active by default — Dragon visible, Fox/Wolf hidden.
    const dragonTile = await screen.findByRole('button', { name: /^Dragon/i });
    expect(dragonTile).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Fox/i })).toBeNull();

    // Switch to the Hatched chapter — Fox visible, Dragon hidden.
    const user = userEvent.setup();
    const hatchedSpine = screen.getByRole('tab', { name: /Hatched/ });
    await user.click(hatchedSpine);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Fox/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /^Dragon/i })).toBeNull();

    // Switch to Silhouettes — Wolf renders as the unknown silhouette button.
    const silhouettesSpine = screen.getByRole('tab', { name: /Silhouettes/ });
    await user.click(silhouettesSpine);
    await waitFor(() => {
      expect(screen.getByLabelText(/unknown species/i)).toBeInTheDocument();
    });
  });
});
