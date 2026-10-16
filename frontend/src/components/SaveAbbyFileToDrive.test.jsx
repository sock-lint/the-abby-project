import { selectDropdown } from '../test/selectDropdown';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { setToken } from '../api/client';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { authorizeGoogleDrive, prepareGoogleDriveAuthorization } from '../utils/googleDrivePicker';
import SaveAbbyFileToDrive from './SaveAbbyFileToDrive';

vi.mock('../utils/googleDrivePicker', () => ({ authorizeGoogleDrive: vi.fn(), prepareGoogleDriveAuthorization: vi.fn() }));
const SOURCE = { source_type: 'ingestion_pdf', source_id: 'pdf-job-1', title: 'Science.pdf', mime_type: 'application/pdf', context: 'Science project' };
const RESOURCE = { id: 'new-drive-copy', title: 'Science.pdf', url: 'https://drive.google.com/file/d/new-drive-copy/view', mime_type: 'application/pdf', resource_type: 'doc' };
const CONFIG = { configured: true, client_id: 'synthetic-client', api_key: 'synthetic-key', app_id: '123456' };
const pageOf = (results = [SOURCE], extras = {}) => ({ count: results.length, next: null, previous: null, results, ...extras });
function deferred() {
  let resolve;
  const promise = new Promise((yes) => { resolve = yes; });
  return { promise, resolve };
}

beforeEach(() => {
  vi.resetAllMocks();
  setToken('synthetic-parent-token');
  prepareGoogleDriveAuthorization.mockResolvedValue(undefined);
  authorizeGoogleDrive.mockResolvedValue('synthetic-drive-token');
  server.use(
    http.get('*/api/auth/google/drive/config/', () => HttpResponse.json(CONFIG)),
    http.get('*/api/auth/google/drive/sources/', () => HttpResponse.json(pageOf())),
  );
});

describe('SaveAbbyFileToDrive', () => {
  it('saves exactly one existing file after an explicit click and renders the confirmed Drive link', async () => {
    const user = userEvent.setup();
    let authorization;
    const upload = spyHandler('post', '*/api/auth/google/drive/upload/', ({ request }) => {
      authorization = request.headers.get('Authorization');
      return RESOURCE;
    });
    server.use(upload.handler);
    const onSaved = vi.fn();
    const onBusyChange = vi.fn();
    render(<SaveAbbyFileToDrive onSaved={onSaved} onBusyChange={onBusyChange} />);
    expect(screen.getByText(/top level of My Drive/)).toHaveTextContent('Each save creates a new copy');
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf Science project' }));
    const trigger = screen.getByRole('button', { name: 'Save to Google Drive' });
    await waitFor(() => expect(trigger).toBeEnabled());
    expect(authorizeGoogleDrive).not.toHaveBeenCalled();
    expect(upload.calls).toHaveLength(0);
    await user.click(trigger);
    await waitFor(() => expect(upload.calls).toHaveLength(1));
    expect(upload.calls[0].url).toMatch(/\/api\/auth\/google\/drive\/upload\/$/);
    expect(upload.calls[0].body).toEqual({ source_type: SOURCE.source_type, source_id: SOURCE.source_id, access_token: 'synthetic-drive-token' });
    expect(authorization).toBe('Token synthetic-parent-token');
    expect(authorizeGoogleDrive).toHaveBeenCalledWith(CONFIG, { signal: expect.any(AbortSignal) });
    expect(onSaved).toHaveBeenCalledWith(RESOURCE);
    expect(onBusyChange.mock.calls).toEqual([[true], [false]]);
    expect(screen.getByRole('link', { name: 'Open in Google Drive' })).toHaveAttribute('href', RESOURCE.url);
    expect(document.body.textContent).not.toContain('synthetic-drive-token');
    expect(JSON.stringify({ ...localStorage })).not.toContain('synthetic-drive-token');
  });

  it('pages through one category and clears selection when changing category', async () => {
    const user = userEvent.setup();
    const requests = spyHandler('get', '*/api/auth/google/drive/sources/', ({ request }) => {
      const params = new URL(request.url).searchParams;
      if (params.get('source_type') === 'project_photo') return pageOf([{ ...SOURCE, source_type: 'project_photo', source_id: 'photo-1', title: 'Robot.jpg', context: 'Robot' }]);
      return params.get('page') === '2'
        ? pageOf([{ ...SOURCE, source_id: 'pdf-job-2', title: 'Page two.pdf' }], { count: 21, previous: '/api/auth/google/drive/sources/?source_type=ingestion_pdf&page=1' })
        : pageOf([SOURCE], { count: 21, next: '/api/auth/google/drive/sources/?source_type=ingestion_pdf&page=2' });
    });
    server.use(requests.handler);
    render(<SaveAbbyFileToDrive />);
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf Science project' }));
    await user.click(screen.getByRole('button', { name: 'Next files' }));
    expect(await screen.findByRole('radio', { name: 'Page two.pdf Science project' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Save to Google Drive' })).toBeDisabled();
    expect(screen.getByText('Page 2 · 21 files')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Previous files' }));
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf Science project' }));
    await selectDropdown(user, screen.getByLabelText('File category'), 'project_photo');
    expect(await screen.findByRole('radio', { name: 'Robot.jpg Robot' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Save to Google Drive' })).toBeDisabled();
    expect(requests.calls.map(({ url }) => [new URL(url).searchParams.get('source_type'), new URL(url).searchParams.get('page')])).toEqual([
      ['ingestion_pdf', '1'], ['ingestion_pdf', '2'], ['ingestion_pdf', '1'], ['project_photo', '1'],
    ]);
  });

  it.each(['project_photo', 'homework_proof', 'creation_photo'])('loads the permitted %s category', async (sourceType) => {
    const user = userEvent.setup();
    const requests = spyHandler('get', '*/api/auth/google/drive/sources/', pageOf([]));
    server.use(requests.handler);
    render(<SaveAbbyFileToDrive />);
    await screen.findByText('No files in this category yet.');
    await selectDropdown(user, screen.getByLabelText('File category'), sourceType);
    await waitFor(() => expect(requests.calls).toHaveLength(2));
    expect(new URL(requests.calls[1].url).searchParams.get('source_type')).toBe(sourceType);
    expect(authorizeGoogleDrive).not.toHaveBeenCalled();
  });

  it('retries a failed list without starting an upload', async () => {
    const user = userEvent.setup();
    server.use(http.get('*/api/auth/google/drive/sources/', () => HttpResponse.json({ error: 'Files could not be loaded.' }, { status: 503 })));
    render(<SaveAbbyFileToDrive />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Files could not be loaded');
    server.use(http.get('*/api/auth/google/drive/sources/', () => HttpResponse.json(pageOf())));
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('radio', { name: 'Science.pdf Science project' })).toBeInTheDocument();
    expect(authorizeGoogleDrive).not.toHaveBeenCalled();
  });

  it('does not upload when Google authorization is cancelled', async () => {
    const user = userEvent.setup();
    authorizeGoogleDrive.mockResolvedValue(null);
    const upload = spyHandler('post', '*/api/auth/google/drive/upload/', RESOURCE);
    server.use(upload.handler);
    render(<SaveAbbyFileToDrive />);
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf Science project' }));
    await user.click(screen.getByRole('button', { name: 'Save to Google Drive' }));
    expect(upload.calls).toHaveLength(0);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save to Google Drive' })).toBeEnabled();
  });

  it('shows a declined grant without starting an upload', async () => {
    const user = userEvent.setup();
    authorizeGoogleDrive.mockRejectedValue(new Error('Allow access to Google Drive, then try again.'));
    const upload = spyHandler('post', '*/api/auth/google/drive/upload/', RESOURCE);
    server.use(upload.handler);
    render(<SaveAbbyFileToDrive />);
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf Science project' }));
    await user.click(screen.getByRole('button', { name: 'Save to Google Drive' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Allow access');
    expect(upload.calls).toHaveLength(0);
  });

  it('shows a rejected source without displaying a saved link', async () => {
    const user = userEvent.setup();
    const upload = spyHandler('post', '*/api/auth/google/drive/upload/', HttpResponse.json({ error: 'This file is no longer available.' }, { status: 404 }));
    server.use(upload.handler);
    const onSaved = vi.fn();
    render(<SaveAbbyFileToDrive onSaved={onSaved} />);
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf Science project' }));
    await user.click(screen.getByRole('button', { name: 'Save to Google Drive' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('no longer available');
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.queryByRole('link', { name: 'Open in Google Drive' })).not.toBeInTheDocument();
  });

  it('does not automatically repeat an ambiguous upload', async () => {
    const user = userEvent.setup();
    const upload = spyHandler('post', '*/api/auth/google/drive/upload/', HttpResponse.json({ error: 'Upstream failure' }, { status: 503 }));
    server.use(upload.handler);
    render(<SaveAbbyFileToDrive />);
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf Science project' }));
    await user.click(screen.getByRole('button', { name: 'Save to Google Drive' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Check My Drive before saving again');
    expect(upload.calls).toHaveLength(1);
    expect(authorizeGoogleDrive).toHaveBeenCalledOnce();
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument();
  });

  it('cancels pending authorization and ignores its late token', async () => {
    const user = userEvent.setup();
    const auth = deferred();
    authorizeGoogleDrive.mockReturnValue(auth.promise);
    const upload = spyHandler('post', '*/api/auth/google/drive/upload/', RESOURCE);
    server.use(upload.handler);
    render(<SaveAbbyFileToDrive />);
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf Science project' }));
    await user.click(screen.getByRole('button', { name: 'Save to Google Drive' }));
    await user.click(screen.getByRole('button', { name: 'Stop waiting' }));
    expect(authorizeGoogleDrive.mock.calls[0][1].signal.aborted).toBe(true);
    await act(async () => auth.resolve('synthetic-late-token'));
    expect(upload.calls).toHaveLength(0);
  });

  it('clears account data and drops late authorization after an account change', async () => {
    const user = userEvent.setup();
    const auth = deferred();
    authorizeGoogleDrive.mockReturnValue(auth.promise);
    const upload = spyHandler('post', '*/api/auth/google/drive/upload/', RESOURCE);
    server.use(upload.handler);
    render(<SaveAbbyFileToDrive />);
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf Science project' }));
    await user.click(screen.getByRole('button', { name: 'Save to Google Drive' }));
    act(() => setToken('synthetic-other-parent-token'));
    await act(async () => auth.resolve('synthetic-late-token'));
    expect(upload.calls).toHaveLength(0);
    expect(screen.getByRole('alert')).toHaveTextContent('Your account changed');
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });

  it('ignores an old account upload response after an account change', async () => {
    const user = userEvent.setup();
    const response = deferred();
    const calls = [];
    server.use(http.post('*/api/auth/google/drive/upload/', async ({ request }) => {
      calls.push(await request.json());
      await response.promise;
      return HttpResponse.json(RESOURCE);
    }));
    const onSaved = vi.fn();
    render(<SaveAbbyFileToDrive onSaved={onSaved} />);
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf Science project' }));
    await user.click(screen.getByRole('button', { name: 'Save to Google Drive' }));
    await waitFor(() => expect(calls).toHaveLength(1));
    act(() => setToken('synthetic-other-parent-token'));
    await act(async () => response.resolve());
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Your account changed');
  });

  it('aborts pending work when unmounted', async () => {
    const user = userEvent.setup();
    const auth = deferred();
    authorizeGoogleDrive.mockReturnValue(auth.promise);
    const onSaved = vi.fn();
    const { unmount } = render(<SaveAbbyFileToDrive onSaved={onSaved} />);
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf Science project' }));
    await user.click(screen.getByRole('button', { name: 'Save to Google Drive' }));
    unmount();
    expect(authorizeGoogleDrive.mock.calls[0][1].signal.aborted).toBe(true);
    await act(async () => auth.resolve('synthetic-late-token'));
    expect(onSaved).not.toHaveBeenCalled();
  });
});
