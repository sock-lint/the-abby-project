import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { resolveGoogleDriveFile } from '../api';
import { setToken } from '../api/client';
import { STORAGE_KEYS } from '../constants/storage';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { pickGoogleDriveFile, prepareGoogleDrivePicker } from '../utils/googleDrivePicker';
import GoogleDrivePickerButton from './GoogleDrivePickerButton';

vi.mock('../utils/googleDrivePicker', () => ({ prepareGoogleDrivePicker: vi.fn(), pickGoogleDriveFile: vi.fn() }));
const CONFIG = { configured: true, client_id: 'synthetic-client', api_key: 'synthetic-key', app_id: '123456' };
const SELECTION = { file_id: 'synthetic-file', access_token: 'synthetic-drive-token' };

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

beforeEach(() => {
  vi.resetAllMocks();
  prepareGoogleDrivePicker.mockResolvedValue(undefined);
  pickGoogleDriveFile.mockResolvedValue(SELECTION);
  localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, 'synthetic-abby-token');
  server.use(http.get('*/api/auth/google/drive/config/', () => HttpResponse.json(CONFIG)));
});

describe('GoogleDrivePickerButton', () => {
  it('loads readiness before enabling a click, and submits a selected file to Django', async () => {
    const user = userEvent.setup();
    const ready = deferred();
    prepareGoogleDrivePicker.mockReturnValue(ready.promise);
    const resolved = spyHandler('post', /\/api\/auth\/google\/drive\/file\/$/, { title: 'School.pdf' });
    server.use(resolved.handler);
    const onOpenChange = vi.fn();
    const { container } = render(<GoogleDrivePickerButton onPick={resolveGoogleDriveFile} onOpenChange={onOpenChange} pdfOnly />);
    expect(screen.getByRole('button', { name: 'Preparing Google Drive…' })).toBeDisabled();
    await waitFor(() => expect(prepareGoogleDrivePicker).toHaveBeenCalledWith(CONFIG));
    await act(async () => ready.resolve());
    await user.click(screen.getByRole('button', { name: 'Choose from Google Drive' }));
    await waitFor(() => expect(resolved.calls).toHaveLength(1));
    expect(resolved.calls[0].body).toEqual(SELECTION);
    expect(resolved.calls[0].url).toMatch(/\/api\/auth\/google\/drive\/file\/$/);
    expect(pickGoogleDriveFile).toHaveBeenCalledWith(CONFIG, { pdfOnly: true, allowUpload: false, signal: expect.any(AbortSignal) });
    expect(onOpenChange.mock.calls).toEqual([[true], [false]]);
    expect(container.textContent).not.toContain(SELECTION.access_token);
    expect(localStorage.getItem(STORAGE_KEYS.AUTH_TOKEN)).toBe('synthetic-abby-token');
    expect(JSON.stringify({ ...localStorage })).not.toContain(SELECTION.access_token);
  });

  it('waits for the onPick callback before enabling another selection', async () => {
    const user = userEvent.setup();
    const saving = deferred();
    const onPick = vi.fn(() => saving.promise);
    const onOpenChange = vi.fn();
    render(<GoogleDrivePickerButton onPick={onPick} onOpenChange={onOpenChange}>Attach Drive file</GoogleDrivePickerButton>);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Attach Drive file' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Attach Drive file' }));
    expect(screen.getByRole('button', { name: 'Choosing from Google Drive…' })).toBeDisabled();
    expect(onPick).toHaveBeenCalledWith(SELECTION);
    expect(onOpenChange.mock.calls).toEqual([[true]]);
    await act(async () => saving.resolve());
    expect(screen.getByRole('button', { name: 'Attach Drive file' })).toBeEnabled();
    expect(onOpenChange.mock.calls).toEqual([[true], [false]]);
  });

  it('passes an explicit resource-upload option to the picker', async () => {
    const user = userEvent.setup();
    const onPick = vi.fn();
    render(<GoogleDrivePickerButton onPick={onPick} allowUpload>Choose or upload with Google Drive</GoogleDrivePickerButton>);
    const trigger = await screen.findByRole('button', { name: 'Choose or upload with Google Drive' });
    await user.click(trigger);
    expect(pickGoogleDriveFile).toHaveBeenCalledWith(CONFIG, { pdfOnly: false, allowUpload: true, signal: expect.any(AbortSignal) });
    expect(onPick).toHaveBeenCalledWith(SELECTION);
  });

  it('handles cancellation without running onPick or showing an error', async () => {
    const user = userEvent.setup();
    pickGoogleDriveFile.mockResolvedValue(null);
    const onPick = vi.fn();
    render(<GoogleDrivePickerButton onPick={onPick} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose from Google Drive' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Choose from Google Drive' }));
    expect(onPick).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Choose from Google Drive' })).toBeEnabled();
  });

  it('shows an actionable popup error and retries', async () => {
    const user = userEvent.setup();
    pickGoogleDriveFile.mockRejectedValueOnce(new Error('Allow pop-ups for Abby, then try Google Drive again.'));
    const onPick = vi.fn();
    render(<GoogleDrivePickerButton onPick={onPick} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose from Google Drive' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Choose from Google Drive' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Allow pop-ups');
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(onPick).toHaveBeenCalledOnce();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('can retry SDK preparation failures', async () => {
    const user = userEvent.setup();
    prepareGoogleDrivePicker.mockRejectedValueOnce(new Error('Check your connection and try again.'));
    render(<GoogleDrivePickerButton onPick={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Check your connection');
    expect(screen.getByRole('button', { name: 'Choose from Google Drive' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose from Google Drive' })).toBeEnabled());
    expect(prepareGoogleDrivePicker).toHaveBeenCalledTimes(2);
  });

  it('reports a failed onPick callback and allows a fresh picker retry', async () => {
    const user = userEvent.setup();
    const onPick = vi.fn().mockRejectedValueOnce(new Error('Your Google Drive access expired. Choose the file again.')).mockResolvedValue(undefined);
    render(<GoogleDrivePickerButton onPick={onPick} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose from Google Drive' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Choose from Google Drive' }));
    expect(screen.getByRole('alert')).toHaveTextContent('access expired');
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(pickGoogleDriveFile).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('honors disabled without allowing a picker or retry', async () => {
    render(<GoogleDrivePickerButton onPick={vi.fn()} disabled />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose from Google Drive' })).toBeDisabled());
    expect(pickGoogleDriveFile).not.toHaveBeenCalled();
  });

  it('aborts on local sign-in changes and ignores late selected files', async () => {
    const user = userEvent.setup();
    const selection = deferred();
    pickGoogleDriveFile.mockReturnValue(selection.promise);
    const onPick = vi.fn();
    render(<GoogleDrivePickerButton onPick={onPick} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose from Google Drive' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Choose from Google Drive' }));
    const signal = pickGoogleDriveFile.mock.calls[0][1].signal;
    act(() => setToken('synthetic-new-abby-token'));
    expect(signal.aborted).toBe(true);
    await act(async () => selection.resolve(SELECTION));
    expect(onPick).not.toHaveBeenCalled();
  });

  it('aborts on cross-tab auth changes but ignores unrelated storage', async () => {
    const user = userEvent.setup();
    const selection = deferred();
    pickGoogleDriveFile.mockReturnValue(selection.promise);
    const onPick = vi.fn();
    render(<GoogleDrivePickerButton onPick={onPick} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose from Google Drive' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Choose from Google Drive' }));
    const signal = pickGoogleDriveFile.mock.calls[0][1].signal;
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: 'abby_theme' })));
    expect(signal.aborted).toBe(false);
    localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, 'synthetic-new-abby-token');
    act(() => window.dispatchEvent(new StorageEvent('storage', { key: STORAGE_KEYS.AUTH_TOKEN })));
    expect(signal.aborted).toBe(true);
    await act(async () => selection.resolve(SELECTION));
    expect(onPick).not.toHaveBeenCalled();
  });

  it('ignores stale config responses after a credential change', async () => {
    const response = deferred();
    server.use(http.get('*/api/auth/google/drive/config/', async () => {
      await response.promise;
      return HttpResponse.json(CONFIG);
    }));
    render(<GoogleDrivePickerButton onPick={vi.fn()} />);
    localStorage.setItem(STORAGE_KEYS.AUTH_TOKEN, 'synthetic-new-abby-token');
    await act(async () => response.resolve());
    expect(prepareGoogleDrivePicker).not.toHaveBeenCalled();
  });

  it('aborts when unmounted and never invokes a late onPick', async () => {
    const user = userEvent.setup();
    const selection = deferred();
    pickGoogleDriveFile.mockReturnValue(selection.promise);
    const onPick = vi.fn();
    const onOpenChange = vi.fn();
    const { unmount } = render(<GoogleDrivePickerButton onPick={onPick} onOpenChange={onOpenChange} />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose from Google Drive' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Choose from Google Drive' }));
    const signal = pickGoogleDriveFile.mock.calls[0][1].signal;
    unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => selection.resolve(SELECTION));
    expect(onPick).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
  });
});
