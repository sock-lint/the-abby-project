import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import Hatchery from './Hatchery';
import { server } from '../../../test/server';
import { selectDropdown } from '../../../test/selectDropdown';
import { spyHandler } from '../../../test/spy';

// Retain the real family/lifecycle/portrait presentation; only optional heavy
// decorative 3D is replaced. Browse checks never press the 3D opt-in button.
vi.mock('../../../pedestal/PedestalPreview', () => ({ default: () => null }));

const base = { id: 1, slug: 'base', name: 'Base', rarity: 'common', catalog_available: true, acquisition_challenges: [] };
const fire = { id: 2, slug: 'fire', name: 'Fire', rarity: 'rare', catalog_available: true, acquisition_challenges: [] };
const ice = { id: 3, slug: 'ice', name: 'Ice', rarity: 'rare', catalog_available: true, acquisition_challenges: [] };
const chick = { id: 101, slug: 'chick', sprite_key: 'cute-chick', name: 'Chick', icon: '🐤', catalog_available: true,
  discovered: false, owned_pet_ids: [], owned_mount_potion_ids: [], available_potions: [base, fire, ice] };
const dragon = { ...chick, id: 102, slug: 'meshtint-dragon', sprite_key: 'meshtint-dragon', name: 'Dragon', icon: '🐉' };
const mushroom = { ...chick, id: 103, slug: 'meshtint-mushroom', sprite_key: 'meshtint-mushroom', name: 'Mushroom', icon: '🍄' };
const bee = { ...chick, id: 104, slug: 'meshtint-bee', sprite_key: 'meshtint-bee', name: 'Bee', available_potions: [base] };
const bat = { ...chick, id: 105, slug: 'meshtint-bat', sprite_key: 'meshtint-bat', name: 'Bat', available_potions: [base] };
const species = [chick, dragon, mushroom, bee, bat];
const egg = { id: 501, slug: 'meshtint-dragon-egg', name: 'Dragon Egg', item_type: 'egg', catalog_available: true,
  pet_species_slug: dragon.slug, pet_species_name: dragon.name, metadata: { species: dragon.slug } };
const potionItem = (potion) => ({ id: 600 + potion.id, slug: `${potion.slug}-potion`, name: `${potion.name} Potion`,
  item_type: 'potion', catalog_available: true, metadata: { variant: potion.slug } });

function mount({ catalogSpecies = species, stable = { pets: [], mounts: [] }, inventory = [], incubation = null, handlers = [] } = {}) {
  const mutations = [];
  const observe = ({ request }) => { if (!['GET', 'HEAD'].includes(request.method)) mutations.push({ method: request.method, url: request.url }); };
  server.events.on('request:start', observe);
  server.use(
    ...handlers,
    http.get('*/api/pets/codex/', () => HttpResponse.json({ species: catalogSpecies, potions: [base, fire, ice],
      totals: { species: catalogSpecies.length, discovered_species: 0, mounts_possible: 11, mounts_owned: 0 } })),
    http.get('*/api/pets/stable/', () => HttpResponse.json(stable)),
    http.get('*/api/inventory/', () => HttpResponse.json(inventory)),
    http.get('*/api/pets/incubations/', () => HttpResponse.json({ incubation, duration_seconds: 86400, server_now: '2026-10-22T12:00:00Z' })),
  );
  const view = render(<MemoryRouter><Hatchery /></MemoryRouter>);
  return { ...view, mutations, stopObserving: () => server.events.removeListener('request:start', observe) };
}

async function explore(user, family) {
  const region = await screen.findByRole('region', { name: 'Explore companions' });
  if (family) await selectDropdown(user, within(region).getByRole('combobox', { name: 'Explore a family' }), family);
  return within(region);
}

describe('Hatchery companion discovery', () => {
  it('browses approved families and exact elemental growth forms without owning ingredients or starting a recipe', async () => {
    const view = mount();
    try {
      const user = userEvent.setup(), discovery = await explore(user);
      expect(discovery.getByRole('combobox', { name: 'Explore a family' })).toHaveTextContent('Chick');
      expect(discovery.getByRole('button', { name: 'Base appearance', exact: true })).toHaveAttribute('aria-pressed', 'true');
      await selectDropdown(user, discovery.getByRole('combobox', { name: 'Explore a family' }), 'Dragon');
      await user.click(discovery.getByRole('button', { name: 'Fire appearance', exact: true }));
      for (const [stage, form] of [['Baby', 'Fire Dragonling'], ['Middle', 'Fire Dragon'], ['Grown', 'Fire Elder Dragon']]) {
        await user.click(discovery.getByRole('button', { name: stage, exact: true }));
        expect(discovery.getByRole('heading', { name: form, exact: true })).toBeInTheDocument();
      }
      await user.click(discovery.getByRole('button', { name: 'Ice appearance', exact: true }));
      await user.click(discovery.getByRole('button', { name: 'Middle', exact: true }));
      expect(discovery.getByRole('heading', { name: 'Ice Dragon', exact: true })).toBeInTheDocument();
      await user.click(discovery.getByRole('button', { name: 'Egg', exact: true }));
      expect(discovery.getByRole('heading', { name: 'Dragon Egg', exact: true })).toBeInTheDocument();
      expect(discovery.queryByRole('heading', { name: /(?:Fire|Ice).*Egg/ })).toBeNull();
      expect(screen.getByText(/No eggs or potions for new hatching yet/)).toBeInTheDocument();
      expect(view.mutations).toEqual([]);
    } finally { view.stopObserving(); }
  });

  it.each(['Bee', 'Bat'])('keeps %s Base-only despite global elemental potion definitions and inventory', async (family) => {
    const view = mount({ inventory: [fire, ice].map((potion) => ({ quantity: 2, item: potionItem(potion) })) });
    try {
      const user = userEvent.setup(), discovery = await explore(user, family);
      expect(discovery.getByRole('button', { name: 'Base appearance', exact: true })).toBeInTheDocument();
      expect(discovery.queryByRole('button', { name: 'Fire appearance', exact: true })).toBeNull();
      expect(discovery.queryByRole('button', { name: 'Ice appearance', exact: true })).toBeNull();
      expect(discovery.queryByText(/Ember|Frost/)).toBeNull();
      expect(view.mutations).toEqual([]);
    } finally { view.stopObserving(); }
  });

  it('keeps browsing separate from the exact owned Egg and Potion recipe selection', async () => {
    const inventory = [{ quantity: 1, item: egg }, ...[base, fire].map((potion) => ({ quantity: 1, item: potionItem(potion) }))];
    const view = mount({ inventory });
    try {
      const user = userEvent.setup();
      await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg', exact: true }), String(egg.id));
      await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion', exact: true }), '601');
      const discovery = await explore(user, 'Mushroom');
      await user.click(discovery.getByRole('button', { name: 'Ice appearance', exact: true }));
      await user.click(discovery.getByRole('button', { name: 'Grown', exact: true }));
      expect(discovery.getByRole('heading', { name: 'Ice Toadstool', exact: true })).toBeInTheDocument();
      expect(screen.getByRole('combobox', { name: 'Egg', exact: true })).toHaveTextContent('Dragon Egg');
      expect(screen.getByRole('combobox', { name: 'Potion', exact: true })).toHaveTextContent('Base Potion');
      expect(screen.getByRole('button', { name: 'Start incubation', exact: true })).toBeEnabled();
      expect(view.mutations).toEqual([]);
    } finally { view.stopObserving(); }
  });

  it('counts saved growing and grown pairs as owned while keeping the exact incubating pair separate', async () => {
    const stable = { pets: [{ id: 201, species: dragon, potion: fire, lifecycle_stage: 'baby', growth_points: 100, evolved_to_mount: false }],
      mounts: [{ id: 202, species: dragon, potion: base, lifecycle_stage: 'grown' }] };
    const incubation = { id: 203, species: dragon, potion_type: ice, egg, potion: potionItem(ice), status: 'incubating', remaining_seconds: 3600, is_ready: false };
    const view = mount({ stable, incubation });
    try {
      const user = userEvent.setup(), discovery = await explore(user, 'Dragon');
      expect(discovery.getByRole('status', { name: 'Appearance collection status' })).toHaveTextContent(/^Owned$/);
      expect(discovery.getByText('2 of 3 appearances collected')).toBeInTheDocument();
      await user.click(discovery.getByRole('button', { name: 'Fire appearance', exact: true }));
      expect(discovery.getByRole('status', { name: 'Appearance collection status' })).toHaveTextContent(/^Owned$/);
      await user.click(discovery.getByRole('button', { name: 'Ice appearance', exact: true }));
      expect(discovery.getByRole('status', { name: 'Appearance collection status' })).toHaveTextContent(/^Incubating$/);
      expect(discovery.getByText('2 of 3 appearances collected')).toBeInTheDocument();
      expect(view.mutations).toEqual([]);
    } finally { view.stopObserving(); }
  });

  it('shows the accepted frozen challenge progress and exact saved-attempt link without enrolling or retrying', async () => {
    const path = '/quests?tab=trials&goal=goal%3A83';
    const challenge = { definition_id: 77, name: 'Ember Grove', offer_available: false, target: '10', duration_days: 180,
      attempt: { id: 'goal:83', name: 'Saved Ember Grove', status: 'active', progress: '7', target: '12', ends_at: null, retry_available: false }, path };
    const view = mount({ catalogSpecies: [{ ...mushroom, available_potions: [base, { ...fire, acquisition_challenges: [challenge] }, ice] }] });
    try {
      const user = userEvent.setup(), discovery = await explore(user, 'Mushroom');
      await user.click(discovery.getByRole('button', { name: 'Fire appearance', exact: true }));
      expect(discovery.getByText('Saved Ember Grove')).toBeInTheDocument();
      expect(discovery.getByText(/7\s*(?:\/|of)\s*12/)).toBeInTheDocument();
      expect(discovery.getByRole('progressbar', { name: 'Saved Ember Grove progress' })).toHaveAttribute('aria-valuenow', '7');
      expect(discovery.getByRole('progressbar', { name: 'Saved Ember Grove progress' })).toHaveAttribute('aria-valuemax', '12');
      expect(discovery.getAllByRole('link').some((link) => link.getAttribute('href') === path)).toBe(true);
      expect(discovery.queryByRole('button', { name: /start|enroll|retry challenge/i })).toBeNull();
      expect(view.mutations).toEqual([]);
    } finally { view.stopObserving(); }
  });

  it('does not turn an unavailable stable read into a claim that no appearances are collected', async () => {
    const view = mount({ handlers: [http.get('*/api/pets/stable/', () => HttpResponse.json({ detail: 'Collection read unavailable' }, { status: 503 }))] });
    try {
      const user = userEvent.setup(), discovery = await explore(user, 'Dragon');
      expect(discovery.getByRole('status', { name: 'Appearance collection status' })).toHaveTextContent('Collection status unavailable');
      expect(discovery.queryByText(/not (?:yet )?(?:owned|collected)|0 (?:of|\/) 3/i)).toBeNull();
      expect(discovery.getByRole('button', { name: 'Fire appearance', exact: true })).toBeEnabled();
      expect(view.mutations).toEqual([]);
    } finally { view.stopObserving(); }
  });

  it('keeps a failed catalog read distinct from an empty collection and restores discovery after retry', async () => {
    let unavailable = true;
    const view = mount({ handlers: [http.get('*/api/pets/codex/', () => unavailable
      ? HttpResponse.json({ detail: 'Companion catalog unavailable' }, { status: 503 })
      : HttpResponse.json({ species, potions: [base, fire, ice] }))] });
    try {
      const discovery = within(await screen.findByRole('region', { name: 'Explore companions' }));
      expect(await screen.findByRole('alert')).toHaveTextContent('Companion catalog unavailable');
      expect(discovery.getByRole('status')).toHaveTextContent(/appearances are unavailable/i);
      expect(discovery.queryByText(/0 (?:of|\/) \d+|nothing collected|no companions collected/i)).toBeNull();
      unavailable = false;
      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: /try again|retry/i }));
      expect(await discovery.findByRole('combobox', { name: 'Explore a family' })).toBeEnabled();
      expect(view.mutations).toEqual([]);
    } finally { view.stopObserving(); }
  });

  it('keeps an accepted ready hatch usable while discovery catalog is loading', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const incubation = { id: 203, species: dragon, potion_type: ice, egg, potion: potionItem(ice), status: 'ready', remaining_seconds: 0, is_ready: true };
    const hatch = spyHandler('post', /\/api\/pets\/incubations\/203\/hatch\/$/, { incubation: { ...incubation, status: 'hatched' },
      pet: { id: 204, species: dragon, potion: ice, lifecycle_stage: 'baby' }, freshly_hatched: false });
    const view = mount({ incubation, handlers: [hatch.handler,
      http.get('*/api/pets/codex/', async () => { await pending; return HttpResponse.json({ species, potions: [base, fire, ice] }); })] });
    try {
      const user = userEvent.setup();
      const hatchButton = await screen.findByRole('button', { name: 'Hatch pet', exact: true });
      const discovery = within(screen.getByRole('region', { name: 'Explore companions' }));
      expect(discovery.getByRole('status')).toHaveTextContent('Loading companion appearances');
      expect(discovery.queryByRole('combobox', { name: 'Explore a family' })).toBeNull();
      expect(discovery.queryByText(/0 (?:of|\/) \d+|nothing collected|no companions collected/i)).toBeNull();
      await user.click(hatchButton);
      expect(await screen.findByRole('link', { name: 'Care for your new pet' })).toHaveAttribute('href', '/bestiary?tab=companions&pet=204');
      await waitFor(() => expect(hatch.calls).toHaveLength(1));
    } finally {
      await act(async () => { release(); await pending; });
      view.stopObserving();
    }
  });
});
