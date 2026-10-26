import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Hatchery from './Hatchery';
import { server } from '../../../test/server';
import { spyHandler } from '../../../test/spy';
import { selectDropdown } from '../../../test/selectDropdown';

vi.mock('../../../pedestal/PedestalPreview', () => ({ default: () => null }));
vi.mock('../PetCeremonyModal', () => ({ default: ({ pet, onDismiss }) =>
  <div role="dialog" aria-label="Hatch celebration" data-species={pet.species.slug} data-potion={pet.potion.slug}>
    <button type="button" onClick={onDismiss}>Close celebration</button>
  </div> }));

// Ordinary application component and API calls; these responses are synthetic
// server-confirmed state, not evidence of production acquisition or artwork.
const pairs = ['meshtint-snake', 'meshtint-hermit-crab'].flatMap((species) => ['fire', 'ice'].map((potion) => [species, potion]));
const names = { 'meshtint-snake': 'Snakelet', 'meshtint-hermit-crab': 'Shell' };
const serverNow = '2026-10-24T10:00:00Z';

function setup(speciesSlug, potionSlug, { ready = false, fresh = true } = {}) {
  const species = { id: speciesSlug === 'meshtint-snake' ? 67 : 68, slug: speciesSlug, sprite_key: speciesSlug,
    name: names[speciesSlug], icon: '🐾', catalog_available: true };
  const potion = { id: potionSlug === 'fire' ? 2 : 3, slug: potionSlug, name: potionSlug === 'fire' ? 'Fire' : 'Ice', catalog_available: true };
  const egg = { id: speciesSlug === 'meshtint-snake' ? 77 : 78, slug: `${speciesSlug}-egg`, name: `${species.name} Egg`,
    item_type: 'egg', icon: '🥚', catalog_available: true, pet_species_slug: speciesSlug, pet_species_name: species.name, metadata: { species: speciesSlug } };
  const ingredient = { id: potionSlug === 'fire' ? 51 : 52, slug: `${potionSlug}-potion`, name: `${potion.name} Potion`,
    item_type: 'potion', catalog_available: true, metadata: { variant: potionSlug } };
  const pet = { id: 900, species, potion, lifecycle_stage: 'baby', evolved_to_mount: false, growth_points: 0 };
  const waiting = { id: 7, egg, potion: ingredient, species, potion_type: potion, started_at: serverNow,
    ready_at: '2026-10-25T10:00:00Z', remaining_seconds: 86400, is_ready: false, status: 'incubating', hatched_at: null, pet_id: null };
  const available = { ...waiting, remaining_seconds: 0, is_ready: true, status: 'ready' };
  let incubation = ready ? available : null;
  const start = spyHandler('post', /\/api\/pets\/incubations\/$/, () => {
    incubation = waiting;
    return HttpResponse.json({ incubation, server_now: serverNow }, { status: 201 });
  });
  const hatch = spyHandler('post', /\/api\/pets\/incubations\/7\/hatch\/$/, () => {
    incubation = null;
    return { incubation: { ...available, status: 'hatched', pet_id: pet.id }, pet, freshly_hatched: fresh, server_now: serverNow };
  });
  const instantHatch = spyHandler('post', /\/api\/pets\/hatch\/$/, {});
  server.use(start.handler, hatch.handler, instantHatch.handler,
    http.get('*/api/pets/codex/', () => HttpResponse.json({ species: [{ ...species, available_potions: [potion] }] })),
    http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [] })),
    http.get('*/api/inventory/', () => HttpResponse.json([{ item: egg, quantity: 1 }, { item: ingredient, quantity: 1 }])),
    http.get('*/api/pets/incubations/', () => HttpResponse.json({ incubation, duration_seconds: 86400, server_now: serverNow })));
  const onChanged = vi.fn();
  const mount = () => render(<MemoryRouter><Hatchery onChanged={onChanged} /></MemoryRouter>);
  return { species, potion, egg, ingredient, pet, start, hatch, instantHatch, mount, onChanged,
    markReady() { incubation = available; } };
}

describe('ordinary Snake/Hermit Crab incubation and hatch', () => {
  it.each(pairs)('starts, restores and explicitly hatches the exact %s %s appearance once', async (species, potion) => {
    const fixture = setup(species, potion), user = userEvent.setup();
    let view = fixture.mount();
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), String(fixture.egg.id));
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), String(fixture.ingredient.id));
    expect(screen.getByText(/Selected appearance:/)).toHaveTextContent(`${fixture.potion.name} ${fixture.species.name}`);
    expect(screen.getByRole('heading', { name: fixture.egg.name })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Egg', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await user.dblClick(screen.getByRole('button', { name: 'Start incubation' }));
    await screen.findByRole('heading', { name: 'Your egg is incubating' });
    expect(fixture.start.calls).toHaveLength(1);
    expect(fixture.start.calls[0]).toMatchObject({ method: 'POST', url: expect.stringMatching(/\/api\/pets\/incubations\/$/),
      body: { egg_item_id: String(fixture.egg.id), potion_item_id: String(fixture.ingredient.id),
        request_id: expect.stringMatching(/^[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}$/i) } });
    expect(within(screen.getByRole('region', { name: 'Your incubating egg' })).getByText(new RegExp(`${fixture.species.name} Egg.*${fixture.potion.name} Potion`))).toBeInTheDocument();
    expect(fixture.hatch.calls).toHaveLength(0);
    expect(fixture.instantHatch.calls).toHaveLength(0);
    expect(screen.queryByRole('dialog', { name: 'Hatch celebration' })).toBeNull();
    view.unmount();
    view = fixture.mount();
    await screen.findByRole('heading', { name: 'Your egg is incubating' });
    expect(fixture.start.calls).toHaveLength(1);
    expect(screen.queryByRole('button', { name: 'Hatch pet' })).toBeNull();
    fixture.markReady();
    fireEvent.focus(window);
    await screen.findByRole('heading', { name: 'Your egg is ready to hatch' });
    expect(fixture.hatch.calls).toHaveLength(0);
    await user.dblClick(screen.getByRole('button', { name: 'Hatch pet' }));
    await waitFor(() => expect(fixture.hatch.calls).toHaveLength(1));
    expect(fixture.hatch.calls[0]).toEqual({ method: 'POST', body: null, url: expect.stringMatching(/\/api\/pets\/incubations\/7\/hatch\/$/) });
    const ceremony = await screen.findByRole('dialog', { name: 'Hatch celebration' });
    expect(ceremony).toHaveAttribute('data-species', species);
    expect(ceremony).toHaveAttribute('data-potion', potion);
    expect(screen.getByRole('link', { name: 'Care for your new pet' })).toHaveAttribute('href', '/bestiary?tab=companions&pet=900');
    expect(screen.getByText(`✨ You hatched a ${fixture.potion.name} ${fixture.species.name}!`)).toBeInTheDocument();
    expect(fixture.instantHatch.calls).toHaveLength(0);
    expect(fixture.onChanged).toHaveBeenCalledTimes(2);
    view.unmount();
  });

  it.each(pairs)('keeps the replayed %s %s hatch identity and care link without another celebration', async (species, potion) => {
    const fixture = setup(species, potion, { ready: true, fresh: false }), user = userEvent.setup();
    fixture.mount();
    await user.click(await screen.findByRole('button', { name: 'Hatch pet' }));
    expect(await screen.findByText(`Your ${fixture.potion.name} ${fixture.species.name} is ready for care.`)).toBeInTheDocument();
    expect(fixture.hatch.calls).toHaveLength(1);
    expect(fixture.hatch.calls[0]).toEqual({ method: 'POST', body: null, url: expect.stringMatching(/\/api\/pets\/incubations\/7\/hatch\/$/) });
    expect(screen.getByRole('link', { name: 'Care for your new pet' })).toHaveAttribute('href', '/bestiary?tab=companions&pet=900');
    expect(screen.queryByRole('dialog', { name: 'Hatch celebration' })).toBeNull();
    expect(fixture.start.calls).toHaveLength(0);
    expect(fixture.instantHatch.calls).toHaveLength(0);
  });
});
