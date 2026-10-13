import { describe, expect, it, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, renderWithProviders, screen, waitFor, userEvent } from '../../test/render';
import { server } from '../../test/server';
import { setToken } from '../../api/client';
import AvatarCustomizer from './AvatarCustomizer';
import { AVATAR_DEFAULTS } from '../../avatar/preferences';
import * as api from '../../api';

vi.mock('./AvatarPreview', () => ({ default: ({ preferences }) => <div role="img" aria-label={`Avatar preview: ${preferences.hair_style}, ${preferences.outfit}`} /> }));

beforeEach(() => {
  setToken('synthetic-avatar-review');
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json({ id: 1, role: 'child', username: 'test' })));
});

describe('AvatarCustomizer', () => {
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
