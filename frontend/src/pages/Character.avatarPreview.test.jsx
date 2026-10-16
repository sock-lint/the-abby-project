import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import Character from './Character';
import { act, renderWithProviders, screen, waitFor } from '../test/render';
import { server } from '../test/server';
import { buildUser } from '../test/factories';
import { spyHandler } from '../test/spy';
import { setToken } from '../api/client';
import { resolveAvatarAppearance } from '../avatar/appearance';
import catalog from '../../../contracts/api/fixtures/avatar-catalog.json';
import defaultProfile from '../../../contracts/api/fixtures/character-avatar-default.json';
import equippedProfile from '../../../contracts/api/fixtures/character-avatar-configuration-saved.json';

const scene = vi.hoisted(() => ({ props: null }));
// Exercise the real Preview, configuration boundary and Profile wiring. Only
// the optional art resolver and WebGL scene are synthetic in this DOM test.
vi.mock('../avatar/appearance', () => ({ resolveAvatarAppearance: vi.fn((preferences) => ({
  url: '/synthetic-profile-archer.glb', hairStyle: preferences.hair_style,
  headStyle: preferences.head_style, textures: {},
  wardrobe: { headwear: preferences.headwear_style, bow: preferences.bow_style },
  preferences,
})) }));
vi.mock('../avatar/AvatarScene', () => ({ default: (props) => {
  scene.props = props;
  return <canvas data-testid="saved-avatar-scene" />;
} }));
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

beforeEach(() => {
  scene.props = null;
  resolveAvatarAppearance.mockClear();
  Element.prototype.scrollIntoView = vi.fn();
  setToken('synthetic-profile-preview-session');
});

function profileRoutes(profile = defaultProfile) {
  const save = spyHandler('post', /\/api\/character\/avatar\/configuration\/$/, {});
  const equip = spyHandler('post', /\/api\/character\/equip\/$/, {});
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ id: profile.id }))),
    http.get('*/api/character/', () => HttpResponse.json(profile)),
    http.get('*/api/cosmetics/', () => HttpResponse.json({})),
    http.get('*/api/cosmetics/catalog/', () => HttpResponse.json({})),
    http.get('*/api/badges/', () => HttpResponse.json([])),
    http.get('*/api/achievements/summary/', () => HttpResponse.json({ badges_earned: [] })),
    save.handler, equip.handler,
  );
  return { save, equip };
}

async function readyProfile(profile, mutations) {
  expect(await screen.findByRole('heading', { name: profile.display_name })).toBeInTheDocument();
  expect(await screen.findByTestId('saved-avatar-scene')).toBeInTheDocument();
  act(() => scene.props.onReady());
  expect(screen.getByRole('group', { name: 'Character view' })).toHaveAttribute('aria-busy', 'false');
  expect(screen.getByRole('img', { name: 'Your Female Archer avatar' })).toBeInTheDocument();
  expect(scene.props.appearance.preferences).toEqual(profile.avatar_preferences);
  expect(screen.getByRole('link', { name: 'Customize avatar' })).toHaveAttribute('href', '/profile/customize');
  expect(screen.getByRole('button', { name: 'Upload picture' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Your look' })).toBeInTheDocument();
  expect(mutations.save.calls).toHaveLength(0);
  expect(mutations.equip.calls).toHaveLength(0);
}

describe('saved Profile avatar without an available options catalog', () => {
  it.each([defaultProfile, equippedProfile])('keeps the confirmed prepared Archer when the catalog returns 503', async (profile) => {
    const mutations = profileRoutes(profile);
    server.use(http.get('*/api/character/avatar/catalog/', () => HttpResponse.json({ error: 'Catalog unavailable.' }, { status: 503 })));
    renderWithProviders(<Character />);
    await readyProfile(profile, mutations);
    expect(resolveAvatarAppearance).toHaveBeenCalledWith(profile.avatar_preferences);
    expect(screen.queryByText('The avatar preview is unavailable. You can still customize your look.')).toBeNull();
  });

  it('shows the saved prepared Archer while the catalog request is still pending', async () => {
    const mutations = profileRoutes();
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const started = vi.fn();
    server.use(http.get('*/api/character/avatar/catalog/', async () => {
      started(); await pending;
      return HttpResponse.json(catalog);
    }));
    renderWithProviders(<Character />);
    try {
      await waitFor(() => expect(started).toHaveBeenCalledOnce());
      await readyProfile(defaultProfile, mutations);
    } finally {
      await act(async () => { release(); await pending; });
    }
  });

  it.each([
    (configuration) => { configuration.avatar_id = 'unprepared-knight'; },
    (configuration) => { configuration.accessories.right_hand = 'unknown-sword'; },
    (configuration) => { configuration.accessories.left_hand = 'unknown-bow'; },
    (configuration) => { delete configuration.appearance.face_style; },
  ])('retains an unavailable preview for unknown or unsupported saved configuration during a catalog outage', async (change) => {
    const profile = structuredClone(defaultProfile);
    change(profile.avatar_configuration);
    const mutations = profileRoutes(profile);
    server.use(http.get('*/api/character/avatar/catalog/', () => HttpResponse.json({ error: 'Catalog unavailable.' }, { status: 503 })));
    renderWithProviders(<Character />);
    await screen.findByRole('heading', { name: profile.display_name });
    expect(screen.getByText('The avatar preview is unavailable. You can still customize your look.')).toBeInTheDocument();
    expect(screen.queryByTestId('saved-avatar-scene')).toBeNull();
    expect(resolveAvatarAppearance).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'Customize avatar' })).toHaveAttribute('href', '/profile/customize');
    expect(mutations.save.calls).toHaveLength(0);
    expect(mutations.equip.calls).toHaveLength(0);
  });
});
