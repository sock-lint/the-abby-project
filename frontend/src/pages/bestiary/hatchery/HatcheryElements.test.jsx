import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Hatchery from './Hatchery';
import { server } from '../../../test/server';
import { spyHandler } from '../../../test/spy';
import { openDropdown, selectDropdown } from '../../../test/selectDropdown';

vi.mock('../../../pedestal/PedestalPreview', () => ({ default: () => null }));
// These scenarios exercise unavailable model art, independently of installed
// private releases. Installed-art rendering has its own preview/browser checks.
vi.mock('../../../companion/sharedElementalRelease', async () => ({
  ...await vi.importActual('../../../companion/sharedElementalRelease'),
  resolveElementalPreviewAppearance: vi.fn(() => null),
}));

const base = { id: 1, slug: 'base', name: 'Base', rarity: 'common' };
const fire = { id: 2, slug: 'fire', name: 'Fire', rarity: 'common' };
const ice = { id: 3, slug: 'ice', name: 'Ice', rarity: 'common' };
const species = [
  { slug: 'chick', name: 'Chick', sprite_key: 'cute-chick', available_potions: [base, fire, ice] },
  { slug: 'meshtint-wolf', name: 'Wolf', sprite_key: 'meshtint-wolf', available_potions: [base, fire, ice] },
  { slug: 'meshtint-bat', name: 'Bat', sprite_key: 'meshtint-bat', available_potions: [base] },
  { slug: 'meshtint-mushroom', name: 'Mushroom', sprite_key: 'meshtint-mushroom', available_potions: [base, fire, ice] },
  { slug: 'meshtint-dragon', name: 'Dragon', sprite_key: 'meshtint-dragon', available_potions: [base, fire, ice] },
].map((family, familyIndex) => ({
  ...family,
  available_potions: family.available_potions.map((potion) => ({
    ...potion,
    acquisition_challenges: potion.slug === 'base' ? [] : [{
      definition_id: 100 + familyIndex * 2 + (potion.slug === 'fire' ? 1 : 2),
      name: (potion.slug === 'fire' ? 'Ember ' : 'Frost ')
        + ({ chick: 'Nest', 'meshtint-wolf': 'Trail', 'meshtint-mushroom': 'Grove', 'meshtint-dragon': 'Summit' })[family.slug],
      offer_available: true, target: String(({ chick: 5, 'meshtint-wolf': 20, 'meshtint-mushroom': 10, 'meshtint-dragon': 50 })[family.slug]),
      duration_days: family.slug === 'meshtint-dragon' ? 365 : 180, attempt: null, path: '/quests?tab=trials',
    }],
  })),
}));
const eggs = species.map((entry, index) => ({ quantity: 1, item: {
  id: 10 + index, slug: `${entry.slug}-egg`, name: `${entry.name} Egg`,
  item_type: 'egg', catalog_available: true, pet_species_slug: entry.slug,
  pet_species_name: entry.name, metadata: { species: entry.slug },
} }));
const potions = [base, fire, ice].map((entry) => ({ quantity: 1, item: {
  id: 20 + entry.id, slug: `${entry.slug}-potion`, name: `${entry.name} Potion`,
  item_type: 'potion', catalog_available: true, metadata: { variant: entry.slug },
} }));

function page(extraHandlers = []) {
  server.use(
    ...extraHandlers,
    http.get('*/api/pets/codex/', () => HttpResponse.json({ species })),
    http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [] })),
    http.get('*/api/inventory/', () => HttpResponse.json([...eggs, ...potions])),
  );
  return render(<MemoryRouter><Hatchery showDiscovery /></MemoryRouter>);
}

describe('Elemental Hatchery choices', () => {
  it.each([[0, fire], [0, ice], [1, fire], [1, ice], [3, fire], [3, ice], [4, fire], [4, ice]])('starts the selected egg %i with its exact $slug potion without showing Base art as its result', async (index, potion) => {
    const egg = eggs[index].item;
    const item = potions.find((entry) => entry.item.metadata.variant === potion.slug).item;
    const start = spyHandler('post', /\/api\/pets\/incubations\/$/, { incubation: { id: 7, egg, potion: item, remaining_seconds: 86400, status: 'incubating', is_ready: false } });
    page([start.handler]);
    const user = userEvent.setup();
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), String(egg.id));
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), String(item.id));
    expect(screen.getByText(/Selected appearance:/)).toHaveTextContent(potion.name);
    const discovery = within(screen.getByRole('region', { name: 'Explore companions' }));
    expect(discovery.getByText(/Challenge target:/)).toHaveTextContent(String(({ 0: 5, 1: 20, 3: 10, 4: 50 })[index]));
    expect(discovery.getByRole('button', { name: potion.name + ' appearance' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: 'Baby' }));
    expect(screen.getByText(`${potion.name} artwork is not available yet. You can still inspect the growth stages and choose your ingredients.`)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Show 3D preview' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Start incubation' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Start incubation' }));
    await waitFor(() => expect(start.calls).toHaveLength(1));
    expect(start.calls[0].body).toEqual({ egg_item_id: String(egg.id), potion_item_id: String(item.id), request_id: expect.any(String) });
  });

  it('clears an incompatible potion after changing egg, and never offers its unsupported appearance', async () => {
    const start = spyHandler('post', /\/api\/pets\/incubations\/$/, {});
    page([start.handler]);
    const user = userEvent.setup();
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), '10');
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), '22');
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Egg' }), '12');
    expect(screen.getByRole('combobox', { name: 'Potion' })).toHaveTextContent('Select a potion…');
    const choices = await openDropdown(user, screen.getByRole('combobox', { name: 'Potion' }));
    expect(choices.queryByRole('option', { name: /Fire Potion|Ice Potion/ })).toBeNull();
    expect(choices.getByRole('option', { name: /Base Potion/ })).toBeInTheDocument();
    const startButton = screen.getByRole('button', { name: 'Start incubation' });
    expect(startButton).toBeDisabled();
    await user.click(startButton);
    expect(start.calls).toHaveLength(0);
    expect(screen.queryByText('Earn Fire and Ice appearances')).toBeNull();
  });

  it('blocks starts while compatibility is unknown, then restores choices from a successful catalog retry', async () => {
    let unavailable = true;
    page([http.get('*/api/pets/codex/', () => unavailable
      ? HttpResponse.json({ detail: 'Potion choices unavailable' }, { status: 503 })
      : HttpResponse.json({ species }))]);
    const user = userEvent.setup();
    expect(await screen.findByRole('alert')).toHaveTextContent('Potion choices unavailable');
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Egg' }), '10');
    expect(screen.getByRole('combobox', { name: 'Potion' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Start incubation' })).toBeDisabled();
    unavailable = false;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Potion' })).toBeEnabled());
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), '23');
    expect(screen.getByRole('button', { name: 'Start incubation' })).toBeEnabled();
  });

  it('keeps an accepted ready hatch usable while compatibility is still loading', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const incubation = { id: 7, egg: eggs[0].item, potion: potions[1].item, remaining_seconds: 0, status: 'ready', is_ready: true };
    const hatch = spyHandler('post', /\/api\/pets\/incubations\/7\/hatch\/$/, { incubation: { ...incubation, status: 'hatched' }, pet: { id: 8, species: species[0], potion: fire }, freshly_hatched: false });
    page([
      http.get('*/api/pets/codex/', async () => { await pending; return HttpResponse.json({ species }); }),
      http.get('*/api/pets/incubations/', () => HttpResponse.json({ incubation })), hatch.handler,
    ]);
    try {
      const user = userEvent.setup();
      await user.click(await screen.findByRole('button', { name: 'Hatch pet' }));
      expect(await screen.findByRole('link', { name: 'Care for your new pet' })).toHaveAttribute('href', '/bestiary?tab=companions&pet=8');
      expect(hatch.calls).toHaveLength(1);
    } finally { await act(async () => { release(); await pending; }); }
  });
});
