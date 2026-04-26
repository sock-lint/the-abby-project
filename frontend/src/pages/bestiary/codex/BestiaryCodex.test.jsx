import { describe, expect, it, vi } from 'vitest';
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
    expect(screen.getByText(/0\/1/)).toBeInTheDocument();
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
    const tile = await screen.findByRole('button', { name: /dragon/i });
    const user = userEvent.setup();
    await user.click(tile);
    await waitFor(() =>
      expect(screen.getByRole('dialog', { name: /dragon/i })).toBeInTheDocument(),
    );
    expect(screen.getByLabelText(/fire dragon — owned/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/base dragon — not yet evolved/i)).toBeInTheDocument();
  });
});
