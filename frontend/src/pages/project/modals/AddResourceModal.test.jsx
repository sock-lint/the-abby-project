import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AddResourceModal from './AddResourceModal.jsx';
import { server } from '../../../test/server.js';
import { spyHandler } from '../../../test/spy.js';
import { setToken } from '../../../api/client.js';
import config from '../../../../../contracts/api/fixtures/google-drive-config.json';

let oauthConfig;
let pickerCallback;
let picker;
let uploadView;
let views;

beforeEach(() => {
  setToken('synthetic-parent-token');
  server.use(http.get('*/api/auth/google/drive/config/', () => HttpResponse.json(config)));
  picker = { dispose: vi.fn(), setVisible: vi.fn() };
  uploadView = { setIncludeFolders: vi.fn().mockReturnThis() };
  const view = { setIncludeFolders: vi.fn().mockReturnThis(), setSelectFolderEnabled: vi.fn().mockReturnThis() };
  const builder = {};
  views = [];
  builder.addView = vi.fn((next) => { views.push(next); return builder; });
  for (const method of ['setOAuthToken', 'setDeveloperKey', 'setAppId', 'setOrigin', 'setTitle']) builder[method] = vi.fn().mockReturnValue(builder);
  builder.setCallback = vi.fn((callback) => { pickerCallback = callback; return builder; });
  builder.build = vi.fn(() => picker);
  window.google = {
    accounts: { oauth2: {
      hasGrantedAllScopes: vi.fn(() => true),
      initTokenClient: vi.fn((next) => { oauthConfig = next; return { requestAccessToken: vi.fn() }; }),
    } },
    picker: {
      DocsView: vi.fn(function () { return view; }),
      DocsUploadView: vi.fn(function () { return uploadView; }),
      PickerBuilder: vi.fn(function () { return builder; }),
      ViewId: { DOCS: 'docs' }, Response: { ACTION: 'action', DOCUMENTS: 'docs' },
      Action: { CANCEL: 'cancel', PICKED: 'picked', ERROR: 'error' },
      Document: { ID: 'id', MIME_TYPE: 'mimeType' },
    },
  };
  window.gapi = { load: vi.fn() };
});

afterEach(() => {
  delete window.google;
  delete window.gapi;
});

async function openPicker(user) {
  const trigger = await screen.findByRole('button', { name: 'Choose or upload with Google Drive' });
  await user.click(trigger);
  act(() => oauthConfig.callback({ access_token: 'synthetic-drive-token', scope: 'https://www.googleapis.com/auth/drive.file' }));
  expect(picker.setVisible).toHaveBeenCalledWith(true);
}

function selectFile(file) {
  act(() => pickerCallback({ action: 'picked', docs: [file] }));
}

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('AddResourceModal', () => {
  it('submits a new resource', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const save = spyHandler('post', '*/api/projects/5/resources/', { id: 1 });
    server.use(save.handler);
    render(
      <AddResourceModal projectId={5} steps={[{ id: 10, title: 'Cut' }]} onClose={vi.fn()} onSaved={onSaved} />,
    );
    await user.type(document.querySelector('input[type="url"]'), 'https://example.com');
    await user.click(screen.getByRole('button', { name: /^add resource$/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(save.calls[0].url).toMatch(/\/api\/projects\/5\/resources\/$/);
    expect(save.calls[0].body).toEqual({ project: 5, title: '', url: 'https://example.com', resource_type: 'link', step: null });
  });

  it('verifies a Drive PDF and saves its link under the chosen project step', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const resolve = spyHandler('post', '*/api/auth/google/drive/file/', {
      id: 'school-pdf-1', title: 'Science worksheet.pdf',
      url: 'https://drive.google.com/file/d/school-pdf-1/view',
      mime_type: 'application/pdf', resource_type: 'doc',
    });
    const save = spyHandler('post', '*/api/projects/5/resources/', { id: 11 });
    server.use(resolve.handler, save.handler);
    render(<AddResourceModal projectId={5} steps={[{ id: 10, title: 'Experiment' }]} onClose={vi.fn()} onSaved={onSaved} />);
    await user.selectOptions(screen.getByLabelText('Attach to Step'), '10');
    await openPicker(user);
    selectFile({ id: 'school-pdf-1', mimeType: 'application/pdf' });
    await waitFor(() => expect(screen.getByLabelText('Title (optional)')).toHaveValue('Science worksheet.pdf'));
    expect(resolve.calls).toHaveLength(1);
    expect(resolve.calls[0].body).toEqual({ file_id: 'school-pdf-1', access_token: 'synthetic-drive-token' });
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: /^add resource$/i }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toEqual({
      project: 5, title: 'Science worksheet.pdf',
      url: 'https://drive.google.com/file/d/school-pdf-1/view', resource_type: 'doc', step: '10',
    });
    expect(onSaved).toHaveBeenCalledOnce();
    expect(document.body.textContent).not.toContain('synthetic-drive-token');
  });

  it('saves an existing Abby PDF to Drive before offering its confirmed link as a resource', async () => {
    const user = userEvent.setup();
    const source = { source_type: 'ingestion_pdf', source_id: 'abby-pdf-1', title: 'Science.pdf', mime_type: 'application/pdf', context: 'School project' };
    const resource = { id: 'new-drive-copy', title: 'Science.pdf', url: 'https://drive.google.com/file/d/new-drive-copy/view', mime_type: 'application/pdf', resource_type: 'doc' };
    server.use(http.get('*/api/auth/google/drive/sources/', () => HttpResponse.json({ count: 1, next: null, previous: null, results: [source] })));
    const upload = spyHandler('post', '*/api/auth/google/drive/upload/', resource);
    const save = spyHandler('post', '*/api/projects/5/resources/', { id: 12 });
    server.use(upload.handler, save.handler);
    const onSaved = vi.fn();
    render(<AddResourceModal projectId={5} steps={[]} onClose={vi.fn()} onSaved={onSaved} />);
    await user.click(screen.getByRole('button', { name: 'Save a file from Abby' }));
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf School project' }));
    const trigger = screen.getByRole('button', { name: 'Save to Google Drive' });
    await waitFor(() => expect(trigger).toBeEnabled());
    await user.click(trigger);
    expect(screen.getByRole('button', { name: 'Choose or upload with Google Drive' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /^add resource$/i })).toBeDisabled();
    act(() => oauthConfig.callback({ access_token: 'synthetic-drive-token', scope: 'https://www.googleapis.com/auth/drive.file' }));
    await waitFor(() => expect(screen.getByLabelText('URL')).toHaveValue(resource.url));
    expect(picker.setVisible).not.toHaveBeenCalled();
    expect(upload.calls).toHaveLength(1);
    expect(upload.calls[0].url).toMatch(/\/api\/auth\/google\/drive\/upload\/$/);
    expect(upload.calls[0].body).toEqual({ source_type: 'ingestion_pdf', source_id: 'abby-pdf-1', access_token: 'synthetic-drive-token' });
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: /^add resource$/i }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toEqual({ project: 5, title: resource.title, url: resource.url, resource_type: 'doc', step: null });
    expect(onSaved).toHaveBeenCalledOnce();
    expect(document.body.textContent).not.toContain('synthetic-drive-token');
  });

  it('disables the inline Abby copy controls while the existing Google picker owns the flow', async () => {
    const user = userEvent.setup();
    server.use(http.get('*/api/auth/google/drive/sources/', () => HttpResponse.json({ count: 1, next: null, previous: null, results: [{ source_type: 'ingestion_pdf', source_id: 'abby-pdf-1', title: 'Science.pdf', mime_type: 'application/pdf', context: 'School project' }] })));
    render(<AddResourceModal projectId={5} steps={[]} onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'Save a file from Abby' }));
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf School project' }));
    await openPicker(user);
    expect(screen.getByRole('button', { name: 'Save to Google Drive' })).toBeDisabled();
    expect(screen.getByLabelText('File category')).toBeDisabled();
    act(() => pickerCallback({ action: 'cancel' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save to Google Drive' })).toBeEnabled());
  });

  it('keeps keyboard focus inside the resource form while waiting for the Abby file upload', async () => {
    const user = userEvent.setup();
    const source = { source_type: 'ingestion_pdf', source_id: 'abby-pdf-1', title: 'Science.pdf', mime_type: 'application/pdf', context: 'School project' };
    let finishUpload;
    const response = new Promise((resolve) => { finishUpload = resolve; });
    let uploadStarted = false;
    server.use(
      http.get('*/api/auth/google/drive/sources/', () => HttpResponse.json({ count: 1, next: null, previous: null, results: [source] })),
      http.post('*/api/auth/google/drive/upload/', async () => {
        uploadStarted = true;
        await response;
        return HttpResponse.json({ id: 'copy', title: 'Science.pdf', url: 'https://drive.google.com/file/d/copy/view', mime_type: 'application/pdf', resource_type: 'doc' });
      }),
    );
    render(<><button type="button">Background action</button><AddResourceModal projectId={5} steps={[]} onClose={vi.fn()} onSaved={vi.fn()} /></>);
    await user.click(screen.getByRole('button', { name: 'Save a file from Abby' }));
    await user.click(await screen.findByRole('radio', { name: 'Science.pdf School project' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Save to Google Drive' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Save to Google Drive' }));
    act(() => oauthConfig.callback({ access_token: 'synthetic-drive-token', scope: 'https://www.googleapis.com/auth/drive.file' }));
    await waitFor(() => expect(uploadStarted).toBe(true));
    const dialog = screen.getByRole('dialog', { name: 'Add Resource' });
    act(() => screen.getByRole('button', { name: 'Background action' }).focus());
    expect(dialog.contains(document.activeElement)).toBe(true);
    act(() => screen.getByLabelText('Attach to Step').focus());
    await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(screen.getByRole('button', { name: 'Stop waiting' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Stop waiting' }));
    await act(async () => finishUpload());
    expect(await screen.findByText(/Stopped waiting for the save/)).toBeInTheDocument();
    expect(screen.getByLabelText('URL')).toHaveValue('');
  });

  it.each([
    { id: 'uploaded-pdf', title: 'New worksheet.pdf', mime_type: 'application/pdf', resource_type: 'doc' },
    { id: 'uploaded-photo', title: 'Experiment.jpg', mime_type: 'image/jpeg', resource_type: 'image' },
    { id: 'uploaded-file', title: 'Materials.txt', mime_type: 'text/plain', resource_type: 'link' },
  ])('verifies uploaded $mime_type metadata before saving the project resource', async (file) => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const verified = { ...file, url: `https://drive.google.com/file/d/${file.id}/view` };
    const resolve = spyHandler('post', '*/api/auth/google/drive/file/', verified);
    const save = spyHandler('post', '*/api/projects/5/resources/', { id: 12 });
    server.use(resolve.handler, save.handler);
    render(<AddResourceModal projectId={5} steps={[]} onClose={vi.fn()} onSaved={onSaved} />);
    const copy = screen.getByText(/uploaded files stay in drive even if you cancel this form/i);
    const trigger = await screen.findByRole('button', { name: 'Choose or upload with Google Drive' });
    expect(copy.compareDocumentPosition(trigger) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await openPicker(user);
    expect(views).toHaveLength(2);
    expect(views[1]).toBe(uploadView);
    expect(uploadView.setIncludeFolders).toHaveBeenCalledWith(true);
    expect(oauthConfig).toMatchObject({ scope: 'https://www.googleapis.com/auth/drive.file', include_granted_scopes: false });
    expect(resolve.calls).toHaveLength(0);
    expect(save.calls).toHaveLength(0);
    selectFile({ id: file.id, mimeType: file.mime_type, name: 'Untrusted picker title', url: 'https://untrusted.example/', resourceKey: 'synthetic-upload-key' });
    await waitFor(() => expect(screen.getByLabelText('Title (optional)')).toHaveValue(file.title));
    expect(resolve.calls).toHaveLength(1);
    expect(resolve.calls[0].url).toMatch(/\/api\/auth\/google\/drive\/file\/$/);
    expect(resolve.calls[0].body).toEqual({ file_id: file.id, access_token: 'synthetic-drive-token', resource_key: 'synthetic-upload-key' });
    expect(screen.getByLabelText('URL')).toHaveValue(verified.url);
    expect(screen.getByLabelText('Type')).toHaveValue(file.resource_type);
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: /^add resource$/i }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].url).toMatch(/\/api\/projects\/5\/resources\/$/);
    expect(save.calls[0].body).toEqual({ project: 5, title: file.title, url: verified.url, resource_type: file.resource_type, step: null });
    expect(onSaved).toHaveBeenCalledOnce();
    expect(document.body.textContent).not.toContain('synthetic-drive-token');
  });

  it('creates no Abby resource when cancelling the Google upload chooser', async () => {
    const user = userEvent.setup();
    const resolve = spyHandler('post', '*/api/auth/google/drive/file/', {});
    const save = spyHandler('post', '*/api/projects/5/resources/', { id: 12 });
    const onSaved = vi.fn();
    server.use(resolve.handler, save.handler);
    render(<AddResourceModal projectId={5} steps={[]} onClose={vi.fn()} onSaved={onSaved} />);
    await openPicker(user);
    act(() => pickerCallback({ action: 'cancel' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose or upload with Google Drive' })).toBeEnabled());
    expect(picker.dispose).toHaveBeenCalledOnce();
    expect(resolve.calls).toHaveLength(0);
    expect(save.calls).toHaveLength(0);
    expect(onSaved).not.toHaveBeenCalled();
    expect(screen.getByLabelText('URL')).toHaveValue('');
  });

  it('does not create an Abby resource when cancelling the form after a Drive upload', async () => {
    const user = userEvent.setup();
    const file = { id: 'uploaded-photo', title: 'Experiment.jpg', url: 'https://drive.google.com/file/d/uploaded-photo/view', mime_type: 'image/jpeg', resource_type: 'image' };
    const resolve = spyHandler('post', '*/api/auth/google/drive/file/', file);
    const save = spyHandler('post', '*/api/projects/5/resources/', { id: 12 });
    const onClose = vi.fn();
    const onSaved = vi.fn();
    server.use(resolve.handler, save.handler);
    render(<AddResourceModal projectId={5} steps={[]} onClose={onClose} onSaved={onSaved} />);
    await openPicker(user);
    selectFile({ id: file.id, mimeType: file.mime_type });
    await waitFor(() => expect(screen.getByLabelText('URL')).toHaveValue(file.url));
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(onClose).toHaveBeenCalledOnce();
    expect(save.calls).toHaveLength(0);
    expect(onSaved).not.toHaveBeenCalled();
    expect(picker.dispose).toHaveBeenCalledOnce();
  });

  it('keeps the resource form available to choose one file after multiple Google uploads', async () => {
    const user = userEvent.setup();
    const file = { id: 'uploaded-photo', title: 'Experiment.jpg', url: 'https://drive.google.com/file/d/uploaded-photo/view', mime_type: 'image/jpeg', resource_type: 'image' };
    const resolve = spyHandler('post', '*/api/auth/google/drive/file/', file);
    const save = spyHandler('post', '*/api/projects/5/resources/', { id: 12 });
    server.use(resolve.handler, save.handler);
    render(<AddResourceModal projectId={5} steps={[]} onClose={vi.fn()} onSaved={vi.fn()} />);
    await openPicker(user);
    act(() => pickerCallback({ action: 'picked', docs: [{ id: 'uploaded-photo' }, { id: 'uploaded-pdf' }] }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Choose one file to attach to this resource. Any uploaded files stay in Google Drive.');
    expect(screen.getByRole('dialog', { name: 'Add Resource' })).toBeInTheDocument();
    expect(resolve.calls).toHaveLength(0);
    expect(save.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    act(() => oauthConfig.callback({ access_token: 'synthetic-drive-token', scope: 'https://www.googleapis.com/auth/drive.file' }));
    selectFile({ id: file.id, mimeType: file.mime_type });
    await waitFor(() => expect(screen.getByLabelText('URL')).toHaveValue(file.url));
    expect(resolve.calls).toHaveLength(1);
    expect(save.calls).toHaveLength(0);
  });

  it('aborts an upload chooser after an Abby account switch and ignores its late selection', async () => {
    const user = userEvent.setup();
    const resolve = spyHandler('post', '*/api/auth/google/drive/file/', {});
    const save = spyHandler('post', '*/api/projects/5/resources/', { id: 12 });
    server.use(resolve.handler, save.handler);
    render(<AddResourceModal projectId={5} steps={[]} onClose={vi.fn()} onSaved={vi.fn()} />);
    await openPicker(user);
    act(() => setToken('synthetic-different-parent-token'));
    selectFile({ id: 'uploaded-photo', mimeType: 'image/jpeg' });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Choose or upload with Google Drive' })).toBeEnabled());
    expect(picker.dispose).toHaveBeenCalledOnce();
    expect(resolve.calls).toHaveLength(0);
    expect(save.calls).toHaveLength(0);
    expect(screen.getByLabelText('URL')).toHaveValue('');
  });
});
