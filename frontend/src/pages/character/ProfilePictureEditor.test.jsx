import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { File as NativeFile } from 'node:buffer';
import { http, HttpResponse } from 'msw';
import { act, renderWithProviders, screen, waitFor, within } from '../../test/render';
import { server } from '../../test/server';
import { buildUser } from '../../test/factories';
import { spyHandler } from '../../test/spy';
import { setToken } from '../../api/client';
import { useAuth } from '../../hooks/useApi';
import * as api from '../../api';
import { downscaleImage } from '../../utils/image';
import ProfilePictureEditor from './ProfilePictureEditor';

vi.mock('../../utils/image', () => ({ downscaleImage: vi.fn(async (file) => file) }));

const previousPicture = '/media/avatars/previous.png';
const nextAccount = buildUser({ id: 2, username: 'next-account', avatar: '/media/avatars/next.png' });

function PictureProbe() {
  const { user, setUser } = useAuth();
  return <>
    <p>{user?.username}</p>
    {user?.avatar && <img src={user.avatar} alt="Saved picture" />}
    <ProfilePictureEditor key={user?.id} />
    <button onClick={() => { setToken('picture-next-session'); setUser(nextAccount); }}>Switch account</button>
  </>;
}

beforeEach(async () => {
  // Keep File/FormData in the same realm as Node's Request implementation.
  // jsdom's separate FormData cannot serialize native files through MSW.
  const nativeFormData = await new Request('https://example.test/', {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: '',
  }).formData();
  vi.stubGlobal('FormData', nativeFormData.constructor);
  setToken('picture-test-session');
  downscaleImage.mockImplementation(async (file) => file);
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ id: 1, avatar: previousPicture }))));
});

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

async function renderEditor() {
  const view = renderWithProviders(<PictureProbe />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Change picture' })).toBeEnabled());
  return view;
}

function pictureFile() {
  // Undici's multipart encoder needs its native File rather than jsdom's
  // separate File implementation to preserve bytes and the filename.
  return new NativeFile(['synthetic-picture'], 'picture.png', { type: 'image/png' });
}

describe('ProfilePictureEditor', () => {
  it('uploads a processed picture as multipart and uses the server-confirmed picture', async () => {
    let submitted, authorization;
    const requestSpy = spyHandler('patch', /\/api\/auth\/me\/$/, ({ request }) => {
      authorization = request.headers.get('Authorization');
      submitted = request.clone().formData();
      return HttpResponse.json(buildUser({ id: 1, avatar: '/media/avatars/saved.png' }));
    });
    server.use(requestSpy.handler);
    const { user } = await renderEditor();
    const file = pictureFile();
    await user.upload(screen.getByLabelText('Upload profile picture'), file);
    expect(await screen.findByText('Profile picture saved.')).toBeInTheDocument();
    expect(requestSpy.calls).toHaveLength(1);
    expect(requestSpy.calls[0].method).toBe('PATCH');
    expect(requestSpy.calls[0].url).toMatch(/\/api\/auth\/me\/$/);
    expect(authorization).toBe('Token picture-test-session');
    const fields = await submitted;
    expect([...fields.keys()]).toEqual(['avatar']);
    expect(fields.get('avatar').name).toBe('picture.png');
    expect(fields.get('avatar').type).toBe('image/png');
    expect(await fields.get('avatar').text()).toBe('synthetic-picture');
    expect(fields.get('avatar').size).toBe(file.size);
    expect(downscaleImage).toHaveBeenCalledWith(file, { maxDim: 512, quality: 0.9 });
    expect(screen.getByRole('img', { name: 'Saved picture' })).toHaveAttribute('src', '/media/avatars/saved.png');
  });

  it('cancels removal without changing the picture or sending a mutation', async () => {
    const request = vi.fn(() => HttpResponse.json({}));
    server.use(http.patch('*/api/auth/me/', request));
    const { user } = await renderEditor();
    await user.click(screen.getByRole('button', { name: 'Remove picture' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(request).not.toHaveBeenCalled();
    expect(screen.getByRole('img', { name: 'Saved picture' })).toHaveAttribute('src', previousPicture);
  });

  it('removes the picture with the existing empty-string API sentinel after confirmation', async () => {
    const requestSpy = spyHandler('patch', /\/api\/auth\/me\/$/, buildUser({ id: 1, avatar: null }));
    server.use(requestSpy.handler);
    const { user } = await renderEditor();
    await user.click(screen.getByRole('button', { name: 'Remove picture' }));
    expect(requestSpy.calls).toHaveLength(0);
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove picture' }));
    expect(await screen.findByText('Profile picture removed.')).toBeInTheDocument();
    expect(requestSpy.calls).toHaveLength(1);
    expect(requestSpy.calls[0]).toMatchObject({ method: 'PATCH', body: { avatar: '' } });
    expect(requestSpy.calls[0].url).toMatch(/\/api\/auth\/me\/$/);
    expect(screen.queryByRole('img', { name: 'Saved picture' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Upload picture' })).toBeEnabled();
  });

  it.each(['upload', 'remove'])('keeps the saved picture and reports a failed %s', async (operation) => {
    const request = vi.fn(() => HttpResponse.json({ error: 'Picture could not be saved.' }, { status: 400 }));
    server.use(http.patch('*/api/auth/me/', request));
    const { user } = await renderEditor();
    if (operation === 'upload') await user.upload(screen.getByLabelText('Upload profile picture'), pictureFile());
    else {
      await user.click(screen.getByRole('button', { name: 'Remove picture' }));
      await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Remove picture' }));
    }
    expect(await screen.findByRole('alert')).toHaveTextContent('Picture could not be saved.');
    expect(request).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('img', { name: 'Saved picture' })).toHaveAttribute('src', previousPicture);
    expect(screen.getByRole('button', { name: 'Change picture' })).toBeEnabled();
  });

  it.each(['switch account', 'unmount'])('does not upload a processed file after %s', async (action) => {
    let finish;
    const pending = new Promise((resolve) => { finish = resolve; });
    downscaleImage.mockReturnValueOnce(pending);
    const request = vi.fn(() => HttpResponse.json({}));
    server.use(http.patch('*/api/auth/me/', request));
    const { user, unmount } = await renderEditor();
    const file = pictureFile();
    await user.upload(screen.getByLabelText('Upload profile picture'), file);
    if (action === 'switch account') await user.click(screen.getByRole('button', { name: 'Switch account' }));
    else unmount();
    await act(async () => { finish(file); await pending; });
    expect(request).not.toHaveBeenCalled();
    if (action === 'switch account') expect(screen.getByRole('img', { name: 'Saved picture' })).toHaveAttribute('src', nextAccount.avatar);
  });

  it.each(['success', 'failure'])('ignores a pending upload %s after the account switches', async (result) => {
    let finish, fail;
    const pending = new Promise((resolve, reject) => { finish = resolve; fail = reject; });
    const upload = vi.spyOn(api, 'uploadAvatar').mockReturnValue(pending);
    const { user } = await renderEditor();
    await user.upload(screen.getByLabelText('Upload profile picture'), pictureFile());
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    await act(async () => {
      if (result === 'success') finish(buildUser({ id: 1, avatar: '/media/avatars/stale.png' }));
      else fail(new Error('Stale upload failure'));
      await pending.catch(() => {});
    });
    expect(screen.getByText('next-account')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Saved picture' })).toHaveAttribute('src', nextAccount.avatar);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.queryByText('Profile picture saved.')).toBeNull();
    expect(screen.getByRole('button', { name: 'Change picture' })).toBeEnabled();
  });
});
