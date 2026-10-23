import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, within } from '@testing-library/react';
import BestiaryHub from './index.jsx';
import { renderWithProviders } from '../../test/render.jsx';
import { server } from '../../test/server.js';
import { buildParent, buildUser } from '../../test/factories.js';
import { selectDropdown } from '../../test/selectDropdown.js';
import { SpriteCatalogProvider } from '../../providers/SpriteCatalogProvider.jsx';

// The owner's child surprise rule through the real Pets pages: children see
// companion forms only for exact appearances they hatched and stages reached.
vi.mock('../../pedestal/PedestalPreview', () => ({ default: () => null }));

const potions = [
  { id: 1, slug: 'base', name: 'Base', rarity: 'common' },
  { id: 2, slug: 'fire', name: 'Fire', rarity: 'uncommon' },
  { id: 3, slug: 'ice', name: 'Ice', rarity: 'uncommon' },
];
const wolf = { id: 21, slug: 'meshtint-wolf', sprite_key: 'meshtint-wolf', name: 'Wolf', icon: '🐺', rarity: 'common', available_potions: potions, catalog_available: true };
const egg = { id: 71, slug: 'meshtint-wolf-egg', name: 'Wolf Egg', item_type: 'egg', pet_species_slug: wolf.slug, pet_species_name: 'Wolf', metadata: { species: wolf.slug }, catalog_available: true };
const supplies = [{ item: egg, quantity: 2 }, ...potions.map((potion) => ({ quantity: 1,
  item: { id: 80 + potion.id, slug: `${potion.slug}-potion`, name: `${potion.name} Potion`, item_type: 'potion', metadata: { variant: potion.slug }, catalog_available: true } }))];
const child = buildUser({ id: 51, is_staff: false });
const pet = (lifecycle_stage, potion = potions[0], over = {}) => ({ id: 91, species: wolf, potion, lifecycle_stage,
  growth_points: { baby: 12, middle: 65 }[lifecycle_stage] ?? 100, evolved_to_mount: false, is_active: true, happiness_level: 'happy', ...over });

function mount({ account = child, pets = [], mounts = [], stable, tab = 'hatchery' } = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(account)),
    http.get('*/api/pets/stable/', () => stable?.() || HttpResponse.json({ pets, mounts, total_possible: 3 })),
    http.get('*/api/pets/codex/', () => HttpResponse.json({ species: [{ ...wolf, discovered: pets.length + mounts.length > 0,
      owned_pet_ids: pets.map(({ id }) => id), owned_mount_potion_ids: mounts.map(({ potion }) => potion.id) }], potions,
    totals: { species: 1, discovered_species: pets.length + mounts.length > 0 ? 1 : 0, mounts_possible: 3, mounts_owned: mounts.length } })),
    http.get('*/api/inventory/', () => HttpResponse.json(supplies)),
    http.get('*/api/pets/incubations/', () => HttpResponse.json({ incubation: null, duration_seconds: 86400, server_now: '2026-10-23T12:00:00Z' })),
    http.get('*/api/sprites/catalog/', () => HttpResponse.json({ etag: 'surprise', sprites: {
      'meshtint-wolf': { url: '/synthetic/base-baby.png', frames: 1, fps: 0 },
      'meshtint-wolf-middle': { url: '/synthetic/base-middle.png', frames: 1, fps: 0 },
      'meshtint-wolf-mount': { url: '/synthetic/base-grown.png', frames: 1, fps: 0 },
    } })),
  );
  return renderWithProviders(<SpriteCatalogProvider><BestiaryHub /></SpriteCatalogProvider>, { route: `/bestiary?tab=${tab}` });
}
async function choose(user, potion) {
  await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), String(egg.id));
  await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), String(80 + potions.find(({ slug }) => slug === potion).id));
}
const stageButtons = () => ['Baby', 'Middle', 'Grown'].filter((name) => screen.queryByRole('button', { name }));
const baseArt = () => document.querySelector('img[src*="/synthetic/base-"]');

describe('Child surprise previews', () => {
  it('keeps an unhatched egg a surprise while its recipe remains usable', async () => {
    const { user } = mount();
    await choose(user, 'base');
    expect(stageButtons()).toEqual([]);
    expect(screen.queryByRole('region', { name: 'Family artwork preview' })).toBeNull();
    expect(screen.queryByText(/Wolf Pup|Werewolf/)).toBeNull();
    expect(baseArt()).toBeNull();
    expect(screen.getByText(/Selected appearance:/)).toHaveTextContent('Selected appearance: Base Wolf.');
    expect(within(screen.getByRole('list', { name: 'Pet growth stages' })).getAllByRole('listitem')).toHaveLength(4);
    expect(screen.getByRole('button', { name: 'Start incubation' })).toBeEnabled();
  });

  it.each([
    ['baby', {}, ['Baby']],
    ['middle', {}, ['Baby', 'Middle']],
    ['middle with 100 growth and no confirmed evolution', { growth_points: 100 }, ['Baby', 'Middle']],
  ])('lets a child revisit only reached stages of an owned %s', async (stage, over, allowed) => {
    const { user } = mount({ pets: [pet(stage.split(' ')[0], potions[0], over)] });
    await choose(user, 'base');
    expect(stageButtons()).toEqual(allowed);
    expect(screen.queryByText(/Werewolf/)).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Baby' }));
    expect(screen.getByRole('heading', { name: 'Wolf Pup' })).toBeInTheDocument();
  });

  it('reveals the grown form only after confirmed evolution', async () => {
    const grown = pet('grown', potions[0], { evolved_to_mount: true });
    const { user } = mount({ pets: [grown], mounts: [{ ...grown, id: 92 }] });
    await choose(user, 'base');
    expect(stageButtons()).toEqual(['Baby', 'Middle', 'Grown']);
    await user.click(screen.getByRole('button', { name: 'Grown' }));
    expect(screen.getByRole('heading', { name: 'Werewolf' })).toBeInTheDocument();
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), '82');
    expect(screen.queryByRole('heading', { name: /Werewolf/ })).toBeNull();
    expect(stageButtons()).toEqual([]);
  });

  it('does not let an owned Fire appearance unlock Base or Ice', async () => {
    const { user } = mount({ pets: [pet('baby', potions[1])] });
    await choose(user, 'base');
    expect(stageButtons()).toEqual([]);
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), '82');
    expect(stageButtons()).toEqual(['Baby']);
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), '83');
    expect(stageButtons()).toEqual([]);
    expect(screen.queryByText(/Ice Wolf Pup/)).toBeNull();
  });

  it('does not treat a legacy potion without a slug as Base', async () => {
    const legacy = pet('middle', { id: 9, slug: null, name: 'Legacy' });
    const { user } = mount({ pets: [legacy] });
    await choose(user, 'base');
    expect(stageButtons()).toEqual([]);
    expect(screen.queryByText(/Wolf Pup|Werewolf/)).toBeNull();
  });

  it('shows no companion art in Collection when ownership cannot be read', async () => {
    const failed = () => HttpResponse.json({ detail: 'Unavailable' }, { status: 503 });
    const { user } = mount({ tab: 'codex', pets: [pet('baby')], stable: failed });
    await user.click(await screen.findByRole('button', { name: /^Wolf —/ }));
    const dialog = await screen.findByRole('dialog');
    expect(baseArt()).toBeNull();
    expect(within(dialog).queryByText(/Wolf Pup|Werewolf/)).toBeNull();
  });

  it('keeps unowned Collection forms and Base stand-ins out of a child view', async () => {
    const { user } = mount({ tab: 'codex', pets: [pet('baby', potions[1])] });
    await user.click(await screen.findByRole('button', { name: /^Wolf —/ }));
    const dialog = await screen.findByRole('dialog');
    expect(baseArt()).toBeNull();
    expect(within(dialog).queryByText(/Werewolf/)).toBeNull();
    expect(within(dialog).queryAllByRole('img', { name: /Werewolf/ })).toHaveLength(0);
    expect(within(dialog).getByRole('img', { name: 'Fire grown form — not yet evolved' })).toBeInTheDocument();
  });

  it('keeps codex-only grown ownership locked for a child when the stable read fails', async () => {
    const failed = () => HttpResponse.json({ detail: 'Unavailable' }, { status: 503 });
    const grown = pet('grown', potions[0], { evolved_to_mount: true });
    const { user } = mount({ tab: 'codex', pets: [grown], mounts: [{ ...grown, id: 92 }], stable: failed });
    expect(await screen.findByRole('alert')).toHaveTextContent('Your companions could not be loaded');
    await user.click(await screen.findByRole('button', { name: /^Wolf —/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('img', { name: 'Base grown form — owned' })).toBeInTheDocument();
    expect(baseArt()).toBeNull();
    expect(within(dialog).queryByText(/Werewolf/)).toBeNull();
  });

  it('keeps parents previewing owned eggs', async () => {
    const parent = buildParent({ id: 52, is_staff: false });
    const { user } = mount({ account: parent });
    await choose(user, 'base');
    expect(screen.queryByRole('region', { name: 'Explore companions' })).toBeNull();
    expect(stageButtons()).toEqual(['Baby', 'Middle', 'Grown']);
    await user.click(screen.getByRole('button', { name: 'Grown' }));
    expect(screen.getByRole('heading', { name: 'Werewolf' })).toBeInTheDocument();
  });

  it('keeps parents viewing every Collection grown form and form name', async () => {
    const { user } = mount({ account: buildParent({ id: 54, is_staff: false }), tab: 'codex', pets: [pet('baby', potions[1])] });
    await user.click(await screen.findByRole('button', { name: /^Wolf —/ }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('img', { name: 'Ice Werewolf — not yet evolved' })).toBeInTheDocument();
    expect(within(dialog).getByText('Grown · Werewolf')).toBeInTheDocument();
  });

  it('draws no Base stand-in or later names in a child Collection while ownership loads', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const { user } = mount({ tab: 'codex', pets: [pet('baby', potions[1])],
      stable: async () => { await pending; return HttpResponse.json({ pets: [pet('baby', potions[1])], mounts: [] }); } });
    await user.click(await screen.findByRole('button', { name: /^Wolf —/ }));
    const dialog = await screen.findByRole('dialog');
    expect(baseArt()).toBeNull();
    expect(within(dialog).queryByText(/· Wolf\b|Werewolf/)).toBeNull();
    release();
    // The owned Fire Pup still never unlocks the Base guide's later names.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(baseArt()).toBeNull();
    expect(within(dialog).queryByText(/· Wolf\b|Werewolf/)).toBeNull();
  });

  it('keeps the complete explorer for staff', async () => {
    mount({ account: buildParent({ id: 53, is_staff: true }) });
    expect(await screen.findByRole('region', { name: 'Explore companions' })).toBeInTheDocument();
    expect(stageButtons()).toEqual(['Baby', 'Middle', 'Grown']);
  });
});
