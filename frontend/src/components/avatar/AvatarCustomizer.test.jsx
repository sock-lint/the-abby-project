import { describe, expect, it, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, renderWithProviders, screen, waitFor, within, userEvent } from '../../test/render';
import { server } from '../../test/server';
import { setToken } from '../../api/client';
import AvatarCustomizer from './AvatarCustomizer';
import { AVATAR_DEFAULTS } from '../../avatar/preferences';
import * as api from '../../api';
import { spyHandler } from '../../test/spy';

vi.mock('./AvatarPreview', () => ({ default: ({ preferences }) => <div role="img" aria-label={`Avatar preview: ${preferences.hair_style}, ${preferences.outfit}`} data-face={preferences.face_style} data-head={preferences.head_style} data-wardrobe={JSON.stringify({ headwear_style: preferences.headwear_style, mask_style: preferences.mask_style, bow_style: preferences.bow_style, quiver_style: preferences.quiver_style })} /> }));

beforeEach(() => {
  setToken('synthetic-avatar-review');
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json({ id: 1, role: 'child', username: 'test' })));
});

describe('AvatarCustomizer', () => {
  it('previews independent wardrobe slots and explicitly saves the complete look without reward actions', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const equipment = { headwear_style: 'hood-mystical', mask_style: 'mask-undercover', bow_style: 'bow-myth', quiver_style: 'quiver-rook' };
    const confirmed = { avatar_preferences: { ...AVATAR_DEFAULTS, hair_style: 'hair-03', ...equipment }, coins: 12, xp: 9 };
    const save = spyHandler('post', /\/api\/character\/avatar\/$/, confirmed);
    const reward = spyHandler('post', /\/api\/(?:character\/equip|rewards\/claim)\/$/, {});
    server.use(save.handler, reward.handler);
    renderWithProviders(<AvatarCustomizer profile={{ avatar_preferences: { ...AVATAR_DEFAULTS, hair_style: 'hair-03' } }} onSaved={onSaved} />);
    await user.click(screen.getByRole('button', { name: 'Customize character' }));
    const section = screen.getByRole('group', { name: 'Wardrobe' });
    const labels = { headwear_style: 'Headwear', mask_style: 'Mask', bow_style: 'Bow', quiver_style: 'Quiver' };
    for (const [key, value] of Object.entries(equipment)) {
      const select = within(section).getByRole('combobox', { name: labels[key] });
      expect(select).toHaveValue('none');
      await user.selectOptions(select, value);
    }
    expect(screen.getByRole('combobox', { name: 'Hair style' })).toHaveValue('hair-03');
    expect(screen.getByRole('img', { name: 'Avatar preview: hair-03, nature' })).toHaveAttribute('data-wardrobe', JSON.stringify(equipment));
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Save character' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toEqual({ avatar_preferences: confirmed.avatar_preferences });
    expect(save.calls[0].url).toMatch(/\/api\/character\/avatar\/$/);
    expect(onSaved).toHaveBeenCalledWith(confirmed);
    expect(reward.calls).toHaveLength(0);
  });

  it('applies coordinated wardrobe colors locally while preserving identity and supports Undo', async () => {
    const user = userEvent.setup();
    const saved = { ...AVATAR_DEFAULTS, hair_style: 'hair-04', hair_color: 'orange', skin_tone: 'tan', face_style: 'face-03', head_style: 'head-01', outfit_style: 'archer-03' };
    const save = spyHandler('post', /\/api\/character\/avatar\/$/, {});
    server.use(save.handler);
    renderWithProviders(<AvatarCustomizer profile={{ avatar_preferences: saved }} onSaved={() => {}} />);
    await user.click(screen.getByRole('button', { name: 'Customize character' }));
    const section = screen.getByRole('group', { name: 'Wardrobe' });
    for (const [label, palette, equipment] of [
      ['Aqua', 'aqua', { headwear_style: 'hood-mystical', mask_style: 'none', bow_style: 'bow-vines', quiver_style: 'quiver-angel' }],
      ['Dark', 'dark', { headwear_style: 'hood-mystical', mask_style: 'mask-undercover', bow_style: 'bow-myth', quiver_style: 'quiver-tale' }],
      ['Fire', 'fire', { headwear_style: 'crown-eve', mask_style: 'none', bow_style: 'bow-myth', quiver_style: 'quiver-tale' }],
      ['Nature', 'nature', { headwear_style: 'none', mask_style: 'mask-undercover', bow_style: 'bow-greenhorn', quiver_style: 'quiver-rook' }],
    ]) {
      await user.click(within(section).getByRole('button', { name: label, exact: true }));
      expect(within(section).getByRole('button', { name: label, exact: true })).toHaveAttribute('aria-pressed', 'true');
      expect(screen.getByRole('img', { name: `Avatar preview: hair-04, ${palette}` })).toHaveAttribute('data-wardrobe', JSON.stringify(equipment));
      expect(screen.getByRole('combobox', { name: 'Outfit', exact: true })).toHaveValue(palette);
      for (const [name, key] of [['Hair style', 'hair_style'], ['Hair color', 'hair_color'], ['Skin tone', 'skin_tone'], ['Face', 'face_style'], ['Ears', 'head_style'], ['Outfit style', 'outfit_style']]) {
        expect(screen.getByRole('combobox', { name, exact: true })).toHaveValue(saved[key]);
      }
    }
    await user.click(within(section).getByRole('button', { name: 'Fire', exact: true }));
    await user.click(screen.getByRole('button', { name: 'Undo changes' }));
    expect(screen.getByRole('combobox', { name: 'Outfit', exact: true })).toHaveValue('nature');
    for (const label of ['Headwear', 'Mask', 'Bow', 'Quiver']) expect(within(section).getByRole('combobox', { name: label })).toHaveValue('none');
    expect(screen.getByRole('button', { name: 'Save character' })).toBeDisabled();
    expect(save.calls).toHaveLength(0);
  });

  it('locks the complete wardrobe during a pending save and preserves unsaved choices after rejection', async () => {
    const user = userEvent.setup();
    let rejectSave;
    const request = vi.spyOn(api, 'saveAvatarPreferences').mockReturnValue(new Promise((_resolve, reject) => { rejectSave = reject; }));
    renderWithProviders(<AvatarCustomizer profile={{ avatar_preferences: AVATAR_DEFAULTS }} onSaved={() => {}} />);
    await user.click(screen.getByRole('button', { name: 'Customize character' }));
    const wardrobe = screen.getByRole('group', { name: 'Wardrobe' });
    await user.click(within(wardrobe).getByRole('button', { name: 'Aqua', exact: true }));
    await user.click(screen.getByRole('button', { name: 'Save character' }));
    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    within(wardrobe).getAllByRole('button').forEach((button) => expect(button).toBeDisabled());
    within(wardrobe).getAllByRole('combobox').forEach((select) => expect(select).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Undo changes' })).toBeDisabled();
    await act(async () => { rejectSave(new Error('Try again later.')); });
    expect(await screen.findByRole('alert')).toHaveTextContent('Try again later.');
    expect(within(wardrobe).getByRole('combobox', { name: 'Headwear' })).toHaveValue('hood-mystical');
    expect(screen.getByRole('button', { name: 'Save character' })).toBeEnabled();
    request.mockRestore();
  });

  it('previews and saves rounded ears independently from the default pointed head', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const confirmed = { avatar_preferences: { ...AVATAR_DEFAULTS, head_style: 'head-01' } };
    const save = spyHandler('post', /\/api\/character\/avatar\/$/, confirmed);
    server.use(save.handler);
    renderWithProviders(<AvatarCustomizer profile={{ avatar_preferences: AVATAR_DEFAULTS }} onSaved={onSaved} />);
    await user.click(screen.getByRole('button', { name: 'Customize character' }));
    expect(screen.getByRole('combobox', { name: 'Ears' })).toHaveValue('head-02');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Ears' }), screen.getByRole('option', { name: 'Rounded' }));
    expect(screen.getByRole('img', { name: 'Avatar preview: hair-01, nature' })).toHaveAttribute('data-head', 'head-01');
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Save character' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toEqual({ avatar_preferences: confirmed.avatar_preferences });
    expect(save.calls[0].url).toMatch(/\/api\/character\/avatar\/$/);
    expect(onSaved).toHaveBeenCalledWith(confirmed);
  });
  it.each([['face-01', 'Face 1'], ['face-02', 'Face 2'], ['face-03', 'Face 3']])('previews and saves the selected %s texture family', async (face_style, label) => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const confirmed = { avatar_preferences: { ...AVATAR_DEFAULTS, hair_color: 'grey', face_style } };
    const save = spyHandler('post', /\/api\/character\/avatar\/$/, confirmed);
    server.use(save.handler);
    renderWithProviders(<AvatarCustomizer profile={{ avatar_preferences: AVATAR_DEFAULTS }} onSaved={onSaved} />);
    await user.click(screen.getByRole('button', { name: 'Customize character' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Face' }), screen.getByRole('option', { name: label }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Hair color' }), 'grey');
    expect(screen.getByRole('img', { name: 'Avatar preview: hair-01, nature' })).toHaveAttribute('data-face', face_style);
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Save character' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toEqual({ avatar_preferences: confirmed.avatar_preferences });
    expect(save.calls[0].url).toMatch(/\/api\/character\/avatar\/$/);
    expect(onSaved).toHaveBeenCalledWith(confirmed);
  });

  it.each(['brown', 'orange', 'grey'])('previews and saves a separate outfit style and %s hair with matching server options', async (hair_color) => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const confirmed = { avatar_preferences: { ...AVATAR_DEFAULTS, outfit_style: 'archer-03', hair_color, outfit: 'fire' } };
    const save = spyHandler('post', /\/api\/character\/avatar\/$/, confirmed);
    server.use(save.handler);
    renderWithProviders(<AvatarCustomizer profile={{ avatar_preferences: AVATAR_DEFAULTS }} onSaved={onSaved} />);
    await user.click(screen.getByRole('button', { name: 'Customize character' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Outfit style' }), 'archer-03');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Hair color' }), hair_color);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Outfit' }), 'fire');
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Save character' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toEqual({ avatar_preferences: confirmed.avatar_preferences });
    expect(save.calls[0].url).toMatch(/\/api\/character\/avatar\/$/);
    expect(onSaved).toHaveBeenCalledWith(confirmed);
  });

  it('shows the avatar immediately and saves appearance through the real API wrapper', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    let requestBody;
    const confirmed = { display_name: 'Abby', avatar_preferences: { ...AVATAR_DEFAULTS, hair_style: 'hair-03', outfit: 'aqua' } };
    server.use(http.post('*/api/character/avatar/', async ({ request }) => {
      requestBody = await request.json();
      return HttpResponse.json(confirmed);
    }));
    renderWithProviders(<AvatarCustomizer profile={{ avatar_preferences: AVATAR_DEFAULTS }} onSaved={onSaved} />);
    expect(screen.getByRole('img', { name: 'Avatar preview: hair-01, nature' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Customize character' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Hair style' }), 'hair-03');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Outfit' }), 'aqua');
    await user.click(screen.getByRole('button', { name: 'Save character' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(confirmed));
    expect(requestBody).toEqual({ avatar_preferences: confirmed.avatar_preferences });
    expect(screen.getByText('Character saved.')).toBeInTheDocument();
  });

  it('keeps the attempted look editable if saving fails', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(http.post('*/api/character/avatar/', () => HttpResponse.json({ error: 'Try again shortly.' }, { status: 503 })));
    renderWithProviders(<AvatarCustomizer profile={{ avatar_preferences: AVATAR_DEFAULTS }} onSaved={onSaved} />);
    await user.click(screen.getByRole('button', { name: 'Customize character' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Hair color' }), 'light');
    await user.click(screen.getByRole('button', { name: 'Save character' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Try again shortly.');
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByRole('combobox', { name: 'Hair color' })).toHaveValue('light');
    expect(screen.getByRole('button', { name: 'Save character' })).toBeEnabled();
  });

  it('undoes unsaved preview choices without a mutation', async () => {
    const user = userEvent.setup();
    const mutation = vi.fn(() => HttpResponse.json({}));
    server.use(http.post('*/api/character/avatar/', mutation));
    renderWithProviders(<AvatarCustomizer profile={{ avatar_preferences: { ...AVATAR_DEFAULTS, skin_tone: 'tan' } }} onSaved={() => {}} />);
    await user.click(screen.getByRole('button', { name: 'Customize character' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Skin tone' }), 'fair');
    await user.click(screen.getByRole('button', { name: 'Undo changes' }));
    expect(screen.getByRole('combobox', { name: 'Skin tone' })).toHaveValue('tan');
    expect(screen.getByRole('button', { name: 'Save character' })).toBeDisabled();
    expect(mutation).not.toHaveBeenCalled();
  });

  it('does not install a delayed save after leaving the profile', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    let finish;
    const pending = new Promise((resolve) => { finish = resolve; });
    const request = vi.spyOn(api, 'saveAvatarPreferences').mockReturnValue(pending);
    const { unmount } = renderWithProviders(<AvatarCustomizer profile={{ avatar_preferences: AVATAR_DEFAULTS }} onSaved={onSaved} />);
    await user.click(screen.getByRole('button', { name: 'Customize character' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Outfit' }), 'fire');
    await user.click(screen.getByRole('button', { name: 'Save character' }));
    await waitFor(() => expect(request).toHaveBeenCalled());
    unmount();
    await act(async () => { finish({ avatar_preferences: { ...AVATAR_DEFAULTS, outfit: 'fire' } }); await pending; });
    expect(onSaved).not.toHaveBeenCalled();
    request.mockRestore();
  });
});
