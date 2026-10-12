import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { fireEvent, renderWithProviders, screen, waitFor, within } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildUser } from '../test/factories';
import { SpriteCatalogContext } from '../providers/spriteCatalog.context';
import ChildDashboard from '../pages/ChildDashboard';
import Companions from '../pages/bestiary/party/Companions';
import Mounts from '../pages/bestiary/party/Mounts';
import BestiaryCodex from '../pages/bestiary/codex/BestiaryCodex';
import CodexSection from '../pages/manage/CodexSection';
import presentation from './presentation.json';
import { getLicensedRpgSprite, resolveLicensedRpgSprite } from './licensedRpgSprites';

vi.mock('./licensedRpgSprites', async () => {
  const actual = await vi.importActual('./licensedRpgSprites');
  return { ...actual, getLicensedRpgSprite: vi.fn() };
});
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const CHICK_PORTRAIT = '/assets/synthetic-owned-chick.png';
const BIRD_PORTRAIT = '/assets/synthetic-owned-bird.png';
const SPECIES = { id: 31, slug: 'chick', name: 'Chick', sprite_key: 'cute-chick', icon: '🐥', catalog_available: true };
const BASE = { id: 41, slug: 'base', name: 'Base', rarity: 'common', catalog_available: true };
const chick = (overrides = {}) => ({
  id: 51, species: SPECIES, potion: BASE, growth_points: 95,
  evolved_to_mount: false, is_active: true, happiness_level: 'happy', ...overrides,
});
const stable = (pets = [], mounts = []) => ({ pets, mounts, total_pets: pets.length, total_mounts: mounts.length, total_possible: 1 });
const manifest = {
  schema_version: presentation.schema_version,
  companion: { id: presentation.companion.id, art_key: 'chick', temporary: false, portrait: 'chick.png' },
};
const art = (name) => ({ 'chick.png': CHICK_PORTRAIT, 'bird.png': BIRD_PORTRAIT })[name];

function renderSurface(ui, catalog = {}) {
  return renderWithProviders(
    <SpriteCatalogContext.Provider value={{ getSpriteMeta: (key) => catalog[key] || null }}>
      {ui}
    </SpriteCatalogContext.Provider>,
  );
}

beforeEach(() => {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
  getLicensedRpgSprite.mockImplementation((key) => resolveLicensedRpgSprite(key, manifest, art));
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.spyOn(window, 'matchMedia').mockImplementation((query) => ({
    matches: query === '(prefers-reduced-motion: reduce)', media: query,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }));
});
afterEach(() => vi.restoreAllMocks());

describe('server-confirmed creatures across React surfaces', () => {
  it.each([
    [false, CHICK_PORTRAIT],
    [true, BIRD_PORTRAIT],
  ])('Today shows the confirmed form at full growth (evolved=%s)', async (evolved, portrait) => {
    server.use(http.get('*/api/pets/stable/', () => HttpResponse.json(stable([
      chick({ growth_points: 100, evolved_to_mount: evolved }),
    ]))));
    renderSurface(<ChildDashboard data={{ next_actions: [] }} reload={vi.fn()} />);
    expect(await screen.findByRole('img', { name: 'Base Chick' })).toHaveAttribute('src', portrait);
    expect(screen.getByRole('button', { name: 'Chick growth' })).toHaveTextContent('100%');
  });

  it('Today never creates an owned companion from staged preview art', async () => {
    server.use(http.get('*/api/pets/stable/', () => HttpResponse.json(stable())));
    renderSurface(<ChildDashboard data={{ next_actions: [] }} reload={vi.fn()} />);
    expect(await screen.findByRole('button', { name: 'Find a pet' })).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'Base Chick' })).toBeNull();
  });

  it('an evolved Today portrait recovers to its own base art without changing confirmed growth', async () => {
    server.use(http.get('*/api/pets/stable/', () => HttpResponse.json(stable([
      chick({ growth_points: 100, evolved_to_mount: true }),
    ]))));
    renderSurface(<ChildDashboard data={{ next_actions: [] }} reload={vi.fn()} />);
    const portrait = await screen.findByRole('img', { name: 'Base Chick' });
    expect(portrait).toHaveAttribute('src', BIRD_PORTRAIT);
    fireEvent.error(portrait);
    expect(screen.getByRole('img', { name: 'Base Chick' })).toHaveAttribute('src', CHICK_PORTRAIT);
    expect(screen.getByRole('button', { name: 'Chick growth' })).toHaveTextContent('100%');
  });

  it('Companions switches to Bird after a confirmed feed and stable refresh', async () => {
    let pet = chick();
    const feed = spyHandler('post', /\/api\/pets\/51\/feed\/$/, () => {
      pet = chick({ growth_points: 100, evolved_to_mount: true });
      return { growth_points: 100, evolved: true, mount_id: 61 };
    });
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json(stable([pet]))),
      http.get('*/api/inventory/', () => HttpResponse.json([
        { id: 71, quantity: 1, item: { id: 81, name: 'Birdseed', item_type: 'food', icon: '🌾' } },
      ])),
      feed.handler,
    );
    const { user } = renderSurface(<Companions />);
    expect(await screen.findByRole('img', { name: 'Base Chick' })).toHaveAttribute('src', CHICK_PORTRAIT);
    await user.click(screen.getByRole('button', { name: 'Care for Base Chick' }));
    await user.click(screen.getByRole('button', { name: /Birdseed/ }));
    await waitFor(() => expect(feed.calls).toHaveLength(1));
    expect(feed.calls[0]).toMatchObject({ method: 'POST', body: { food_item_id: 81 } });
    expect(feed.calls[0].url).toMatch(/\/pets\/51\/feed\/$/);
    const ceremony = await screen.findByRole('alertdialog', { name: 'Base Chick' });
    expect(within(ceremony).getByRole('img', { name: 'Chick' })).toHaveAttribute('src', BIRD_PORTRAIT);
    await user.click(within(ceremony).getByRole('button', { name: /Continue/ }));
    expect(screen.getByRole('img', { name: 'Base Chick' })).toHaveAttribute('src', BIRD_PORTRAIT);
    expect(screen.getByRole('button', { name: 'Care for Base Chick' })).toHaveTextContent('evolved');
  });

  it('Mounts uses Bird for Chick while an existing species keeps its own artwork', async () => {
    server.use(http.get('*/api/pets/stable/', () => HttpResponse.json(stable([], [
      { id: 61, species: SPECIES, potion: BASE, is_active: true, last_bred_at: null, catalog_available: true, can_breed: false },
      { id: 62, species: { id: 32, name: 'Fox', sprite_key: 'fox', icon: '🦊', catalog_available: false }, potion: BASE, is_active: false, last_bred_at: null, catalog_available: false, can_breed: false },
    ]))));
    renderSurface(<Mounts />, { 'fox-mount': { url: '/sprites/owned-fox-mount.png', frames: 1 } });
    expect(await screen.findByRole('img', { name: 'Base Chick' })).toHaveAttribute('src', BIRD_PORTRAIT);
    expect(screen.getByRole('img', { name: 'Base Fox' })).toHaveAttribute('src', '/sprites/owned-fox-mount.png');
  });

  it.each([false, true])('Codex shows species and evolution art with the real ownership label (owned=%s)', async (owned) => {
    server.use(http.get('*/api/pets/codex/', () => HttpResponse.json({
      species: [{ ...SPECIES, discovered: true, owned_pet_ids: [51], owned_mount_potion_ids: owned ? [BASE.id] : [], available_potions: [BASE] }],
      potions: [BASE], totals: { species: 1, discovered_species: 1, mounts_possible: 1, mounts_owned: owned ? 1 : 0 },
    })));
    const { user } = renderSurface(<BestiaryCodex />);
    expect(await screen.findByRole('img', { name: 'Chick' })).toHaveAttribute('src', CHICK_PORTRAIT);
    await user.click(screen.getByRole('button', { name: `Chick — ${owned ? 1 : 0} of 1 grown pets collected` }));
    const detail = screen.getByRole('dialog', { name: 'Chick' });
    expect(within(detail).getByRole('img', { name: 'Chick' })).toHaveAttribute('src', CHICK_PORTRAIT);
    const variant = within(detail).getByRole('img', { name: `Base Chick — ${owned ? 'owned' : 'not yet evolved'}` });
    expect(within(variant).getByRole('img', { name: 'cute-chick-mount' })).toHaveAttribute('src', BIRD_PORTRAIT);
    if (!owned) expect(variant).toHaveTextContent('locked');
  });

  it('Manage browses the server catalog with Chick and Bird forms', async () => {
    localStorage.setItem('manage:codex:active-section', 'creatures');
    server.use(http.get('*/api/pets/species/catalog/', () => HttpResponse.json([
      { ...SPECIES, available_potions: [BASE] },
    ])));
    const { user } = renderSurface(<CodexSection />);
    expect(await screen.findByRole('img', { name: 'Chick' })).toHaveAttribute('src', CHICK_PORTRAIT);
    await user.click(screen.getByRole('tab', { name: 'Grown pets, 1 entries' }));
    expect(screen.getByRole('img', { name: 'Chick' })).toHaveAttribute('src', BIRD_PORTRAIT);
    await user.click(screen.getByRole('button', { name: /Chick.*grown pet/ }));
    const detail = screen.getByRole('dialog', { name: 'Chick mount' });
    expect(within(detail).getByRole('img', { name: 'Chick' })).toHaveAttribute('src', CHICK_PORTRAIT);
    expect(within(detail).getByRole('img', { name: 'Chick mount' })).toHaveAttribute('src', BIRD_PORTRAIT);
  });
});
