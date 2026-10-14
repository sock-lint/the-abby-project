import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { Link, Route, Routes } from 'react-router-dom';
import { act, renderWithProviders, screen, waitFor, userEvent } from '../../test/render';
import { server } from '../../test/server';
import { buildUser } from '../../test/factories';
import { spyHandler } from '../../test/spy';
import { setToken } from '../../api/client';
import * as api from '../../api';
import CustomizeAvatarPage from './index';
import { archerConfiguration, syntheticCatalog } from './catalog.fixtures';
import { resetAvatarDrafts } from './draftStore';

vi.mock('../../components/avatar/AvatarPreview', () => ({ default: ({ configuration, avatarDefinition }) => <div role="img" aria-label={`Your ${avatarDefinition.label} avatar`} data-configuration={JSON.stringify(configuration)} /> }));
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');return { ...actual, AnimatePresence: ({ children }) => children };
});
const onlyArcher = { ...syntheticCatalog, avatars: [syntheticCatalog.avatars[0]] };
beforeEach(() => { resetAvatarDrafts();setToken('synthetic-customize-session'); });
function routes({ role = 'child', catalog = onlyArcher, configuration = archerConfiguration } = {}) {
  let saved = structuredClone(configuration);
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ id: 41, role }))),
    http.get('*/api/character/', () => HttpResponse.json({ avatar_configuration: saved, coins: 13, xp: 7 })),
    http.get('*/api/character/avatar/catalog/', () => HttpResponse.json(catalog)),
  );
  return { saved: (configuration) => { saved = structuredClone(configuration); } };
}
function page() {
  return renderWithProviders(<><Link to="/elsewhere">Other screen</Link><Routes>
    <Route path="/profile/customize" element={<CustomizeAvatarPage />} />
    <Route path="/profile" element={<div>Saved Profile<Link to="/profile/customize">Return to editor</Link></div>} />
    <Route path="/elsewhere" element={<Link to="/profile/customize">Return to editor</Link>} />
  </Routes></>, { route: '/profile/customize' });
}
async function open() {
  const view = page();await screen.findByRole('group', { name: 'Wardrobe' });return view;
}

describe('dedicated avatar customization session', () => {
  it.each(['child', 'parent'])('explicitly saves only the %s account’s generic configuration and reloads the confirmed choices', async (role) => {
    const user = userEvent.setup();const state = routes({ role });
    const configuration = { ...archerConfiguration, accessories: { ...archerConfiguration.accessories, left_hand: 'bow-greenhorn', back: 'quiver-rook' } };
    const save = spyHandler('post', /\/api\/character\/avatar\/configuration\/$/, { avatar_configuration: configuration, coins: 13, xp: 7 });
    const equip = spyHandler('post', /\/api\/character\/equip\/$/, {});
    server.use(save.handler, equip.handler);
    const view = await open();
    expect(screen.queryByRole('combobox', { name: 'Avatar', exact: true })).toBeNull();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Weapon' }), 'bow-greenhorn');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Back accessory' }), 'quiver-rook');
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Save avatar' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toEqual({ avatar_configuration: configuration });
    expect(new URL(save.calls[0].url).pathname).toBe('/api/character/avatar/configuration/');
    expect(new URL(save.calls[0].url).searchParams.has('user_id')).toBe(false);
    expect(equip.calls).toHaveLength(0);
    expect(await screen.findByText('Avatar saved.')).toBeInTheDocument();
    state.saved(configuration);view.unmount();await open();
    expect(screen.getByRole('combobox', { name: 'Weapon' })).toHaveValue('bow-greenhorn');
    expect(screen.getByRole('combobox', { name: 'Back accessory' })).toHaveValue('quiver-rook');
    expect(screen.getByRole('button', { name: 'Save avatar' })).toBeDisabled();
  });

  it('retains a failed draft across shell navigation and Undo restores server-confirmed state', async () => {
    const user = userEvent.setup();routes();
    server.use(http.post('*/api/character/avatar/configuration/', () => HttpResponse.json({ avatar_configuration: { accessories: { left_hand: ['unsupported'] } } }, { status: 400 })));
    await open();await user.selectOptions(screen.getByRole('combobox', { name: 'Weapon' }), 'bow-greenhorn');
    const unload = new Event('beforeunload', { cancelable: true });window.dispatchEvent(unload);expect(unload.defaultPrevented).toBe(true);
    await user.click(screen.getByRole('button', { name: 'Save avatar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Some avatar choices could not be saved');
    expect(screen.getByRole('alert')).not.toHaveTextContent('avatar_configuration');
    await user.click(screen.getByRole('link', { name: 'Other screen' }));
    await user.click(screen.getByRole('link', { name: 'Return to editor' }));
    expect(await screen.findByRole('combobox', { name: 'Weapon' })).toHaveValue('bow-greenhorn');
    await user.click(screen.getByRole('button', { name: 'Undo changes' }));
    expect(screen.getByRole('combobox', { name: 'Weapon' })).toHaveValue('none');
    const cleanUnload = new Event('beforeunload', { cancelable: true });window.dispatchEvent(cleanUnload);expect(cleanUnload.defaultPrevented).toBe(false);
  });

  it.each([{}, { avatar_configuration: { ...archerConfiguration, appearance: {} } }, { avatar_configuration: { ...archerConfiguration, avatar_id: 'wrong-base' } }])('retains edits when a successful status cannot confirm a complete matching saved configuration', async (response) => {
    const user = userEvent.setup();routes();
    server.use(http.post('*/api/character/avatar/configuration/', () => HttpResponse.json(response)));
    await open();await user.selectOptions(screen.getByRole('combobox', { name: 'Weapon' }), 'bow-greenhorn');
    await user.click(screen.getByRole('button', { name: 'Save avatar' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not confirm the saved avatar');
    expect(screen.getByRole('combobox', { name: 'Weapon' })).toHaveValue('bow-greenhorn');
    expect(screen.queryByText('Avatar saved.')).toBeNull();
    expect(screen.getByRole('button', { name: 'Save avatar' })).toBeEnabled();
  });

  it('guards Back with a discard confirmation and clears only the unsaved draft', async () => {
    const user = userEvent.setup();routes();await open();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Weapon' }), 'bow-greenhorn');
    await user.click(screen.getByRole('button', { name: 'Back to Profile' }));
    expect(screen.getByRole('alertdialog', { name: 'Unsaved avatar changes' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('combobox', { name: 'Weapon' })).toHaveValue('bow-greenhorn');
    await user.click(screen.getByRole('button', { name: 'Back to Profile' }));
    await user.click(screen.getByRole('button', { name: 'Discard and leave' }));
    expect(await screen.findByText('Saved Profile')).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Return to editor' }));
    expect(await screen.findByRole('combobox', { name: 'Weapon' })).toHaveValue('none');
  });

  it('saves the same shared bow/quiver IDs on an explicitly compatible synthetic second base and permits its sword/shield', async () => {
    const user = userEvent.setup();routes({ catalog: syntheticCatalog });
    const expected = { avatar_id: 'synthetic-knight', appearance: { armor_style: 'steel', crest_style: 'none' }, accessories: { headwear: 'none', face_accessory: 'none', left_hand: 'bow-greenhorn', right_hand: 'sword-long', back: 'quiver-rook' } };
    const save = spyHandler('post', /\/api\/character\/avatar\/configuration\/$/, { avatar_configuration: expected });server.use(save.handler);
    await open();await user.selectOptions(screen.getByRole('combobox', { name: 'Headwear' }), 'hood-mystical');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Weapon' }), 'bow-greenhorn');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Back accessory' }), 'quiver-rook');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Avatar', exact: true }), 'synthetic-knight');
    expect(screen.getByRole('combobox', { name: 'Weapon' })).toHaveValue('bow-greenhorn');
    expect(screen.getByRole('combobox', { name: 'Back accessory' })).toHaveValue('quiver-rook');
    expect(screen.getByRole('status')).toHaveTextContent('Mystical hood');
    expect(screen.getByRole('combobox', { name: 'Headwear' })).toHaveValue('none');
    expect(screen.getByRole('option', { name: 'Round shield' })).toHaveValue('shield-round');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Right hand accessory' }), 'sword-long');
    await user.click(screen.getByRole('button', { name: 'Save avatar' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toEqual({ avatar_configuration: expected });
  });

  it('recovers an unknown saved base only after an explicit choice and Undo restores the unavailable state', async () => {
    const user = userEvent.setup();routes({ configuration: { ...archerConfiguration, avatar_id: 'retired-base' } });page();
    await user.click(await screen.findByRole('button', { name: 'Choose Female Archer' }));
    expect(screen.getByRole('group', { name: 'Wardrobe' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save avatar' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Undo changes' }));
    expect(screen.getByRole('button', { name: 'Choose Female Archer' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Your Saved avatar' })).toHaveAttribute('data-configuration', JSON.stringify({ ...archerConfiguration, avatar_id: 'retired-base' }));
  });

  it('ignores an old save after a same-account credential rotation and restores no previous credential draft', async () => {
    const user = userEvent.setup();routes();
    let finish;
    const pending = new Promise((resolve) => { finish = resolve; });
    const request = vi.spyOn(api, 'saveAvatarConfiguration').mockReturnValue(pending);
    const view = await open();await user.selectOptions(screen.getByRole('combobox', { name: 'Weapon' }), 'bow-greenhorn');
    await user.click(screen.getByRole('button', { name: 'Save avatar' }));await waitFor(() => expect(request).toHaveBeenCalledOnce());
    await act(async () => { setToken('synthetic-rotated-session'); });
    expect(screen.queryByRole('combobox', { name: 'Weapon' })).toBeNull();
    // AuthProvider clears its user immediately on a same-tab credential
    // replacement. A fresh authenticated boot represents the new session.
    view.unmount();const replacement = await open();
    await act(async () => { finish({ avatar_configuration: { ...archerConfiguration, accessories: { ...archerConfiguration.accessories, left_hand: 'bow-greenhorn' } } });await pending; });
    expect(screen.getByRole('combobox', { name: 'Weapon' })).toHaveValue('none');
    expect(screen.queryByText('Avatar saved.')).toBeNull();
    replacement.unmount();request.mockRestore();
  });

  it('keeps a failed read recoverable and retries the catalog without any save', async () => {
    const user = userEvent.setup();routes();let fail = true;
    server.use(http.get('*/api/character/avatar/catalog/', () => fail ? HttpResponse.json({ error: 'Catalog temporarily unavailable.' }, { status: 503 }) : HttpResponse.json(onlyArcher)));
    page();expect(await screen.findByRole('alert')).toHaveTextContent('Catalog temporarily unavailable.');
    fail = false;await user.click(screen.getByRole('button', { name: 'Retry customization' }));
    expect(await screen.findByRole('group', { name: 'Wardrobe' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save avatar' })).toBeDisabled();
  });
});
