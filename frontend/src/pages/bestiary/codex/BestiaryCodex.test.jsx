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

function renderCodex(props = {}) {
  return render(
    <MemoryRouter>
      <BestiaryCodex {...props} />
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
  const catalog = {
    species: [
      { id: 1, slug: 'dragon', name: 'Dragon', icon: '🐉', sprite_key: 'dragon', available_potions: samplePotions, discovered: true, owned_pet_ids: [12], owned_mount_potion_ids: [] },
      { id: 2, slug: 'wolf', name: 'Wolf', icon: '🐺', sprite_key: 'wolf', available_potions: samplePotions, discovered: false, owned_pet_ids: [], owned_mount_potion_ids: [] },
    ],
    potions: samplePotions,
    totals: { species: 2, discovered_species: 1, mounts_possible: 4, mounts_owned: 0 },
  };

  it('counts each species’s compatible appearances instead of the global potion catalog', async () => {
    const ice = { id: 3, slug: 'ice', name: 'Ice', rarity: 'uncommon' };
    const all = [...samplePotions, ice];
    server.use(http.get('*/api/pets/codex/', () => HttpResponse.json({
      species: [
        { id: 1, slug: 'meshtint-bat', name: 'Bat', sprite_key: 'meshtint-bat', discovered: true, available_potions: [samplePotions[0]], owned_pet_ids: [1], owned_mount_potion_ids: [] },
        { id: 2, slug: 'meshtint-wolf', name: 'Wolf', sprite_key: 'meshtint-wolf', discovered: true, available_potions: all, owned_pet_ids: [2], owned_mount_potion_ids: [] },
      ],
      potions: all, totals: { species: 2, discovered_species: 2, mounts_possible: 4, mounts_owned: 0 },
    })));
    renderCodex();
    expect(await screen.findByRole('button', { name: 'Bat — 0 of 1 grown pets collected' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Wolf — 0 of 3 grown pets collected' })).toBeInTheDocument();
  });

  it('reports a failed catalog load instead of an empty collection and retries the real request', async () => {
    let requests = 0;
    server.use(http.get('*/api/pets/codex/', () => {
      requests += 1;
      return requests === 1
        ? HttpResponse.json({ detail: 'The pet collection is temporarily unavailable.' }, { status: 503 })
        : HttpResponse.json(catalog);
    }));
    const user = userEvent.setup();
    renderCodex();
    expect(await screen.findByRole('alert')).toHaveTextContent('The pet collection is temporarily unavailable.');
    expect(screen.queryByText('No pet species are available yet.')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('button', { name: /^Dragon/ })).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
    expect(requests).toBe(2);
  });

  it('keeps the current collection and selected group visible when a refresh fails', async () => {
    let requests = 0;
    server.use(http.get('*/api/pets/codex/', () => {
      requests += 1;
      return requests === 2
        ? HttpResponse.json({ detail: 'Could not refresh the collection.' }, { status: 503 })
        : HttpResponse.json(catalog);
    }));
    const user = userEvent.setup();
    const view = renderCodex();
    await screen.findByRole('button', { name: /^Dragon/ });
    await user.click(screen.getByRole('tab', { name: /^Undiscovered/ }));
    const tile = screen.getByLabelText(/unknown species/i);
    view.rerender(<MemoryRouter><BestiaryCodex refreshRevision={1} /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not refresh the collection.');
    expect(screen.getByLabelText(/unknown species/i)).toBe(tile);
    expect(screen.getByRole('tab', { name: /^Undiscovered/ })).toHaveAttribute('aria-selected', 'true');
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(requests).toBe(3));
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
    expect(screen.getByRole('tab', { name: /^Undiscovered/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByLabelText(/unknown species/i)).toBe(tile);
  });

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
    expect(screen.getByRole('region', { name: 'Evolved' })
      .querySelector('[data-chapter-marker="2"]')).toHaveTextContent('2');

    // Switch to the Hatched chapter — Fox visible, Dragon hidden.
    const user = userEvent.setup();
    const hatchedSpine = screen.getByRole('tab', { name: /Hatched/ });
    await user.click(hatchedSpine);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Fox/i })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /^Dragon/i })).toBeNull();
    expect(screen.getByRole('region', { name: 'Hatched' })
      .querySelector('[data-chapter-marker="3"]')).toHaveTextContent('3');

    // Switch to Silhouettes — Wolf renders as the unknown silhouette button.
    const silhouettesSpine = screen.getByRole('tab', { name: /Undiscovered/ });
    await user.click(silhouettesSpine);
    await waitFor(() => {
      expect(screen.getByLabelText(/unknown species/i)).toBeInTheDocument();
    });
  });
});
