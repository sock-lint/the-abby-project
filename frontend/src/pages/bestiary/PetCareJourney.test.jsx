import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { useLocation, useNavigate } from 'react-router-dom';
import { act, renderWithProviders, screen, within, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { selectDropdown } from '../../test/selectDropdown';
import BestiaryHub from './index';
import Hatchery from './hatchery/Hatchery';
import Companions from './party/Companions';

vi.mock('../../components/companion/CompanionPreview', () => ({
  default: ({ children }) => <section aria-label="Companion home">{children}</section>,
}));
vi.mock('../../pedestal/PedestalPreview', () => ({ default: () => null }));
vi.mock('./PetCeremonyModal', () => ({
  default: ({ onDismiss }) => <div role="dialog"><button onClick={onDismiss}>Close pet celebration</button></div>,
}));

const species = { id: 42, slug: 'meshtint-bat', name: 'Bat', sprite_key: 'meshtint-bat', icon: '🐾', catalog_available: true };
const potion = { id: 41, slug: 'base', name: 'Base', rarity: 'common', catalog_available: true };
const baby = { id: 7, name: 'Pip', species, potion, lifecycle_stage: 'baby', growth_points: 49, is_active: false, evolved_to_mount: false, catalog_available: true };
const egg = { quantity: 1, item: { id: 11, slug: 'meshtint-bat-egg', name: 'Bat Egg', item_type: 'egg', pet_species_slug: species.slug, pet_species_name: species.name, metadata: { species: species.slug } } };
const base = { quantity: 1, item: { id: 22, slug: 'base-potion', name: 'Base Potion', item_type: 'potion', metadata: { variant: 'base' } } };
const food = { quantity: 2, item: { id: 33, name: 'Berries', item_type: 'food' } };

beforeEach(() => server.use(http.get('*/api/pets/codex/', () => HttpResponse.json({ species: [{ ...species, available_potions: [potion] }] }))));

function Location() {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  return <><output aria-label="Current page">{pathname}{search}</output>
    <button onClick={() => navigate('/bestiary?tab=hatchery')}>Navigate to Hatchery</button></>;
}

function setup({ pets = [], inventory = [] } = {}) {
  server.use(
    http.get('*/api/pets/stable/', () => HttpResponse.json({ pets, mounts: [], total_possible: 15 })),
    http.get('*/api/inventory/', () => HttpResponse.json(inventory)),
  );
}

describe('Pet care journey', () => {
  it.each([{ name: 'empty inventory', inventory: [] }, { name: 'egg without potion', inventory: [egg] }])('connects missing hatching supplies to challenge rewards without spending ingredients: $name', async ({ inventory }) => {
    setup({ inventory });
    const mutation = spyHandler('post', /\/api\/pets\//, {});
    server.use(mutation.handler);
    const { user } = renderWithProviders(<><Hatchery /><Location /></>, { withAuth: false });
    const guide = await screen.findByRole('region', { name: 'Find hatching supplies' });
    expect(within(guide).getByText(/matching egg and potion bundle/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Explore companions' })).toBeNull();
    expect(within(guide).queryByText(/Explore companions in the Hatchery/)).toBeNull();
    if (inventory.length) expect(screen.getByRole('button', { name: 'Select Bat Egg' })).toBeInTheDocument();
    await user.click(within(guide).getByRole('link', { name: 'View challenge rewards' }));
    expect(screen.getByRole('status', { name: 'Current page' })).toHaveTextContent('/quests?tab=trials');
    expect(mutation.calls).toHaveLength(0);
  });

  it('shows food acquisition actions in the care panel without feeding on navigation', async () => {
    setup({ pets: [baby] });
    const feed = spyHandler('post', /\/api\/pets\/7\/feed\/$/, {});
    server.use(feed.handler);
    const { user } = renderWithProviders(<><Companions /><Location /></>);
    await user.click(await screen.findByRole('button', { name: 'Feed your companion' }));
    const care = screen.getByRole('dialog', { name: 'Care for Pip' });
    const guide = within(care).getByRole('region', { name: 'Find food' });
    await user.click(within(guide).getByRole('link', { name: 'Go to tasks' }));
    expect(screen.getByRole('status', { name: 'Current page' })).toHaveTextContent('/quests');
    expect(feed.calls).toHaveLength(0);
  });

  it('hands a confirmed hatch directly to the new baby care panel', async () => {
    let hatched = false;
    let incubation = null;
    const waiting = { id: 7, egg: egg.item, potion: base.item, remaining_seconds: 7200, is_ready: false, status: 'incubating' };
    const start = spyHandler('post', /\/api\/pets\/incubations\/$/, () => {
      incubation = waiting;
      return { incubation, server_now: '2026-10-18T10:00:00Z' };
    });
    const hatch = spyHandler('post', /\/api\/pets\/incubations\/7\/hatch\/$/, () => {
      hatched = true;
      incubation = null;
      return HttpResponse.json({ pet: { ...baby, growth_points: 0 }, incubation: { ...waiting, status: 'hatched', pet_id: baby.id }, freshly_hatched: true, server_now: '2026-10-18T12:00:00Z' }, { status: 201 });
    });
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: hatched ? [{ ...baby, growth_points: 0 }] : [], mounts: [], total_possible: 15 })),
      http.get('*/api/inventory/', () => HttpResponse.json(hatched ? [food] : [egg, base, food])),
      http.get('*/api/pets/incubations/', () => HttpResponse.json({ incubation, duration_seconds: 7200, server_now: '2026-10-18T10:00:00Z' })),
      start.handler, hatch.handler,
    );
    const { user } = renderWithProviders(<><BestiaryHub /><Location /></>, { route: '/bestiary?tab=hatchery' });
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), '11');
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), '22');
    await user.click(screen.getByRole('button', { name: 'Start incubation' }));
    await screen.findByRole('heading', { name: 'Your egg is incubating' });
    expect(hatch.calls).toHaveLength(0);
    incubation = { ...waiting, is_ready: true, remaining_seconds: 0, status: 'ready' };
    await user.click(screen.getByRole('button', { name: 'Check readiness' }));
    await user.click(await screen.findByRole('button', { name: 'Hatch pet' }));
    await user.click(await screen.findByRole('button', { name: 'Close pet celebration' }));
    await user.click(screen.getByRole('link', { name: 'Care for your new pet' }));
    expect(await screen.findByRole('dialog', { name: 'Care for Pip' })).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Current page' })).toHaveTextContent('/bestiary?tab=companions&pet=7');
    expect(hatch.calls).toHaveLength(1);
    expect(start.calls).toHaveLength(1);
    expect(start.calls[0]).toMatchObject({ method: 'POST', body: { egg_item_id: '11', potion_item_id: '22', request_id: expect.any(String) } });
    expect(hatch.calls[0]).toMatchObject({ method: 'POST', body: null });
    expect(new URL(hatch.calls[0].url).pathname).toBe('/api/pets/incubations/7/hatch/');
    await user.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog', { name: 'Care for Pip' })).toBeNull();
    expect(screen.getByRole('status', { name: 'Current page' })).not.toHaveTextContent('pet=');
  });

  it('ignores a pet link that is not in the signed-in collection without sending mutations', async () => {
    setup({ pets: [baby], inventory: [food] });
    const feed = spyHandler('post', /\/api\/pets\/\d+\/feed\/$/, {});
    server.use(feed.handler);
    renderWithProviders(<Companions />, { route: '/bestiary?tab=companions&pet=999' });
    await screen.findByRole('button', { name: 'Feed your companion' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(feed.calls).toHaveLength(0);
  });

  it('keeps the current tab when a feed finishes after navigating away from linked care', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    setup({ pets: [baby], inventory: [food] });
    const feed = spyHandler('post', /\/api\/pets\/7\/feed\/$/, async () => {
      await pending;
      return { new_growth: 54, growth_added: 5, evolved: false, lifecycle_stage: 'middle' };
    });
    server.use(feed.handler);
    const { user } = renderWithProviders(<><BestiaryHub /><Location /></>, { route: '/bestiary?tab=companions&pet=7' });
    const care = await screen.findByRole('dialog', { name: 'Care for Pip' });
    await user.click(within(care).getByRole('button', { name: /Berries/ }));
    await waitFor(() => expect(feed.calls).toHaveLength(1));
    await user.click(screen.getByRole('button', { name: 'Navigate to Hatchery' }));
    await screen.findByRole('heading', { name: 'Hatchery', exact: true });
    await act(async () => { release(); await pending; });
    // The retained care tab can reconcile its receipt without taking over navigation.
    await screen.findByText(/Pip reached the Middle stage/);
    expect(screen.getByRole('status', { name: 'Current page' })).toHaveTextContent('/bestiary?tab=hatchery');
    expect(screen.getByRole('tab', { name: 'Hatchery' })).toHaveAttribute('aria-selected', 'true');
    expect(feed.calls).toHaveLength(1);
  });

  it('acknowledges a server-confirmed Middle transition once and does not reward a read', async () => {
    let grown = false;
    setup({ inventory: [food] });
    const feed = spyHandler('post', /\/api\/pets\/7\/feed\/$/, () => {
      grown = true;
      return { new_growth: 54, growth_added: 5, evolved: false, lifecycle_stage: 'middle' };
    });
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [{ ...baby, lifecycle_stage: grown ? 'middle' : 'baby', growth_points: grown ? 54 : 49 }], mounts: [], total_possible: 15 })),
      feed.handler,
    );
    const { user } = renderWithProviders(<Companions />);
    await user.click(await screen.findByRole('button', { name: 'Feed your companion' }));
    await user.click(within(screen.getByRole('dialog', { name: 'Care for Pip' })).getByRole('button', { name: /Berries/ }));
    expect(await screen.findByRole('status')).toHaveTextContent('Pip reached the Middle stage');
    await waitFor(() => expect(screen.getByRole('tab', { name: 'Middle (1)' })).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: 'Middle (1)' }));
    expect(feed.calls).toHaveLength(1);
    expect(feed.calls[0]).toMatchObject({ method: 'POST', body: { food_item_id: 33 } });
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
