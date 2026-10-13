import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const CONFIG = { configured: true, client_id: 'synthetic-client', api_key: 'synthetic-key', app_id: '123456' };
let sdk;
let oauth;
let pickerCallback;
let picker;
let view;
let uploadView;
let builder;

function installSdk() {
  picker = { dispose: vi.fn(), setVisible: vi.fn() };
  view = { setIncludeFolders: vi.fn().mockReturnThis(), setSelectFolderEnabled: vi.fn().mockReturnThis(), setMimeTypes: vi.fn().mockReturnThis() };
  uploadView = { setIncludeFolders: vi.fn().mockReturnThis() };
  builder = {};
  for (const method of ['addView', 'setOAuthToken', 'setDeveloperKey', 'setAppId', 'setOrigin', 'setTitle']) {
    builder[method] = vi.fn().mockReturnValue(builder);
  }
  builder.setCallback = vi.fn((callback) => { pickerCallback = callback; return builder; });
  builder.build = vi.fn(() => picker);
  oauth = {
    hasGrantedAllScopes: vi.fn(() => true),
    initTokenClient: vi.fn((config) => {
      oauth.config = config;
      return { requestAccessToken: oauth.requestAccessToken };
    }),
    requestAccessToken: vi.fn(),
  };
  window.google = { accounts: { oauth2: oauth }, picker: {
    PickerBuilder: vi.fn(function () { return builder; }),
    DocsView: vi.fn(function () { return view; }),
    DocsUploadView: vi.fn(function () { return uploadView; }),
    ViewId: { DOCS: 'docs' }, Response: { ACTION: 'action', DOCUMENTS: 'docs' },
    Action: { CANCEL: 'cancel', PICKED: 'picked', ERROR: 'error' },
    Document: { ID: 'id', MIME_TYPE: 'mimeType' },
  } };
  window.gapi = { load: vi.fn() };
}

function authorize() {
  oauth.config.callback({ access_token: 'synthetic-drive-token', scope: sdk.GOOGLE_DRIVE_SCOPE });
}

beforeEach(async () => {
  vi.resetModules();
  sdk = await import('./googleDrivePicker');
  installSdk();
});

afterEach(() => {
  delete window.google;
  delete window.gapi;
  document.querySelectorAll('script[src^="https://accounts.google.com/"], script[src^="https://apis.google.com/"]').forEach((script) => script.remove());
  vi.useRealTimers();
});

describe('Google Drive picker', () => {
  it('authorizes an Abby file save directly from the click without opening a picker', async () => {
    await sdk.prepareGoogleDriveAuthorization(CONFIG);
    const result = sdk.authorizeGoogleDrive(CONFIG);
    expect(oauth.requestAccessToken).toHaveBeenCalledWith({ prompt: 'select_account' });
    expect(oauth.config).toMatchObject({ scope: sdk.GOOGLE_DRIVE_SCOPE, include_granted_scopes: false });
    authorize();
    await expect(result).resolves.toBe('synthetic-drive-token');
    expect(builder.build).not.toHaveBeenCalled();
  });

  it('loads only Identity Services for saving an Abby file', async () => {
    delete window.google;
    delete window.gapi;
    const result = sdk.prepareGoogleDriveAuthorization(CONFIG);
    expect(document.querySelectorAll('script')).toHaveLength(1);
    const script = document.querySelector('script');
    expect(script.src).toBe('https://accounts.google.com/gsi/client');
    installSdk();
    script.dispatchEvent(new Event('load'));
    await expect(result).resolves.toBeUndefined();
    expect(window.gapi.load).not.toHaveBeenCalled();
  });

  it('drops a late direct-authorization token after cancellation', async () => {
    const controller = new AbortController();
    const result = sdk.authorizeGoogleDrive(CONFIG, { signal: controller.signal });
    controller.abort();
    authorize();
    await expect(result).resolves.toBeNull();
  });

  it('cancels a closed direct-authorization popup without selecting a file', async () => {
    const result = sdk.authorizeGoogleDrive(CONFIG);
    oauth.config.error_callback({ type: 'popup_closed' });
    await expect(result).resolves.toBeNull();
  });

  it('rejects a declined direct-authorization grant without exposing raw errors', async () => {
    const result = sdk.authorizeGoogleDrive(CONFIG);
    oauth.config.callback({ error: 'access_denied', error_description: 'synthetic-secret' });
    await expect(result).rejects.toThrow('access was not granted');
  });

  it('requires drive.file on direct authorization', async () => {
    oauth.hasGrantedAllScopes.mockReturnValue(false);
    const result = sdk.authorizeGoogleDrive(CONFIG);
    authorize();
    await expect(result).rejects.toThrow('Allow access');
  });

  it('uses least-privilege OAuth and resolves only a selected file and an ephemeral token', async () => {
    await sdk.prepareGoogleDrivePicker(CONFIG);
    const result = sdk.pickGoogleDriveFile(CONFIG);
    expect(oauth.requestAccessToken).toHaveBeenCalledWith({ prompt: 'select_account' });
    expect(oauth.config).toMatchObject({ client_id: CONFIG.client_id, scope: sdk.GOOGLE_DRIVE_SCOPE, include_granted_scopes: false });
    authorize();
    expect(oauth.hasGrantedAllScopes).toHaveBeenCalledWith(expect.objectContaining({ access_token: 'synthetic-drive-token' }), sdk.GOOGLE_DRIVE_SCOPE);
    expect(builder.setOrigin).toHaveBeenCalledWith(window.location.origin);
    expect(builder.setAppId).toHaveBeenCalledWith(CONFIG.app_id);
    expect(builder.setDeveloperKey).toHaveBeenCalledWith(CONFIG.api_key);
    expect(builder.setOAuthToken).toHaveBeenCalledWith('synthetic-drive-token');
    expect(picker.setVisible).toHaveBeenCalledWith(true);
    pickerCallback({ action: 'loaded' });
    pickerCallback({ action: 'picked', docs: [{ id: 'file-123', name: 'Untrusted title', url: 'https://untrusted.example' }] });
    await expect(result).resolves.toEqual({ file_id: 'file-123', access_token: 'synthetic-drive-token' });
    expect(picker.dispose).toHaveBeenCalledOnce();
  });

  it('passes an optional resource key for link-shared school files', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG);
    authorize();
    pickerCallback({ action: 'picked', docs: [{ id: 'file-123', resourceKey: 'synthetic-resource-key' }] });
    await expect(result).resolves.toEqual({ file_id: 'file-123', access_token: 'synthetic-drive-token', resource_key: 'synthetic-resource-key' });
  });

  it('offers Google-managed uploads and folder selection only when requested', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG, { allowUpload: true });
    authorize();
    expect(window.google.picker.DocsUploadView).toHaveBeenCalledOnce();
    expect(uploadView.setIncludeFolders).toHaveBeenCalledWith(true);
    expect(builder.addView.mock.calls).toEqual([[view], [uploadView]]);
    expect(builder.setTitle).toHaveBeenCalledWith('Choose or upload a project resource');
    expect(oauth.config).toMatchObject({ scope: sdk.GOOGLE_DRIVE_SCOPE, include_granted_scopes: false });
    pickerCallback({ action: 'picked', docs: [{ id: 'uploaded-photo', mimeType: 'image/jpeg', resourceKey: 'synthetic-upload-key' }] });
    await expect(result).resolves.toEqual({ file_id: 'uploaded-photo', access_token: 'synthetic-drive-token', resource_key: 'synthetic-upload-key' });
    expect(picker.dispose).toHaveBeenCalledOnce();
  });

  it('never offers unfiltered uploads in a PDF-only chooser, even if upload is requested', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG, { pdfOnly: true, allowUpload: true });
    authorize();
    expect(view.setMimeTypes).toHaveBeenCalledWith('application/pdf');
    expect(window.google.picker.DocsUploadView).not.toHaveBeenCalled();
    expect(builder.addView.mock.calls).toEqual([[view]]);
    pickerCallback({ action: 'cancel' });
    await expect(result).resolves.toBeNull();
  });

  it('keeps upload disabled for existing choose-only consumers', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG);
    authorize();
    expect(window.google.picker.DocsUploadView).not.toHaveBeenCalled();
    expect(builder.addView.mock.calls).toEqual([[view]]);
    pickerCallback({ action: 'cancel' });
    await expect(result).resolves.toBeNull();
  });

  it('asks for one resource when Google returns multiple uploaded files', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG, { allowUpload: true });
    authorize();
    pickerCallback({ action: 'picked', docs: [{ id: 'uploaded-photo' }, { id: 'uploaded-pdf' }] });
    await expect(result).rejects.toThrow('Choose one file to attach to this resource. Any uploaded files stay in Google Drive.');
    expect(picker.dispose).toHaveBeenCalledOnce();
  });

  it('filters PDFs and rejects a non-PDF selection', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG, { pdfOnly: true });
    authorize();
    expect(view.setMimeTypes).toHaveBeenCalledWith('application/pdf');
    pickerCallback({ action: 'picked', docs: [{ id: 'file-123', mimeType: 'image/png' }] });
    await expect(result).rejects.toThrow('Choose a PDF');
    expect(picker.dispose).toHaveBeenCalledOnce();
  });

  it('accepts a PDF selection', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG, { pdfOnly: true });
    authorize();
    pickerCallback({ action: 'picked', docs: [{ id: 'file-123', mimeType: 'application/pdf' }] });
    await expect(result).resolves.toEqual({ file_id: 'file-123', access_token: 'synthetic-drive-token' });
  });

  it('cancels cleanly and ignores late picker callbacks', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG);
    authorize();
    pickerCallback({ action: 'cancel' });
    pickerCallback({ action: 'picked', docs: [{ id: 'file-123' }] });
    await expect(result).resolves.toBeNull();
    expect(picker.dispose).toHaveBeenCalledOnce();
  });

  it('aborts before OAuth completes without opening a picker', async () => {
    const controller = new AbortController();
    const result = sdk.pickGoogleDriveFile(CONFIG, { signal: controller.signal });
    controller.abort();
    authorize();
    await expect(result).resolves.toBeNull();
    expect(builder.build).not.toHaveBeenCalled();
  });

  it('aborts an open picker and permits future use', async () => {
    const controller = new AbortController();
    const result = sdk.pickGoogleDriveFile(CONFIG, { signal: controller.signal });
    authorize();
    controller.abort();
    await expect(result).resolves.toBeNull();
    expect(picker.dispose).toHaveBeenCalledOnce();
    const retry = sdk.pickGoogleDriveFile(CONFIG);
    oauth.config.error_callback({ type: 'popup_closed' });
    await expect(retry).resolves.toBeNull();
  });

  it('returns immediately when already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(sdk.pickGoogleDriveFile(CONFIG, { signal: controller.signal })).resolves.toBeNull();
    expect(oauth.initTokenClient).not.toHaveBeenCalled();
  });

  it.each(['access_denied', 'invalid_grant'])('explains OAuth %s without displaying raw Google responses', async (error) => {
    const result = sdk.pickGoogleDriveFile(CONFIG);
    oauth.config.callback({ error, error_description: 'synthetic-secret-should-not-render' });
    await expect(result).rejects.toThrow('Google Drive access was not granted');
  });

  it('explains declined Drive scope and never builds the picker', async () => {
    oauth.hasGrantedAllScopes.mockReturnValue(false);
    const result = sdk.pickGoogleDriveFile(CONFIG);
    authorize();
    await expect(result).rejects.toThrow('Allow access');
    expect(builder.build).not.toHaveBeenCalled();
  });

  it('treats a closed sign-in popup as cancellation', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG);
    oauth.config.error_callback({ type: 'popup_closed' });
    await expect(result).resolves.toBeNull();
  });

  it('explains blocked sign-in popups', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG);
    oauth.config.error_callback({ type: 'popup_failed_to_open' });
    await expect(result).rejects.toThrow('Allow pop-ups');
  });

  it('explains a missing selected file', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG);
    authorize();
    pickerCallback({ action: 'picked', docs: [] });
    await expect(result).rejects.toThrow('did not return a file');
  });

  it('handles Picker error callbacks, including revoked access, without exposing raw details', async () => {
    const result = sdk.pickGoogleDriveFile(CONFIG);
    authorize();
    pickerCallback({ action: 'error', error: 'synthetic-secret-details' });
    await expect(result).rejects.toThrow('Check your access and try again');
    expect(picker.dispose).toHaveBeenCalledOnce();
  });

  it('settles when picker construction fails', async () => {
    builder.build.mockImplementation(() => { throw new Error('synthetic-secret'); });
    const result = sdk.pickGoogleDriveFile(CONFIG);
    authorize();
    await expect(result).rejects.toThrow('could not open');
  });

  it('rejects unavailable configuration before loading third-party scripts', async () => {
    await expect(sdk.prepareGoogleDrivePicker({ configured: false })).rejects.toThrow('not available');
    expect(document.querySelectorAll('script')).toHaveLength(0);
  });

  it('waits for both scripts and the picker module to become ready', async () => {
    delete window.google;
    delete window.gapi;
    const preparing = sdk.prepareGoogleDrivePicker(CONFIG);
    expect(document.querySelectorAll('script')).toHaveLength(2);
    installSdk();
    delete window.google.picker;
    document.querySelectorAll('script').forEach((script) => script.dispatchEvent(new Event('load')));
    await Promise.resolve();
    await Promise.resolve();
    expect(window.gapi.load).toHaveBeenCalledWith('picker', expect.objectContaining({ callback: expect.any(Function) }));
    window.google.picker = { PickerBuilder: function () {} };
    window.gapi.load.mock.calls[0][1].callback();
    await expect(preparing).resolves.toBeUndefined();
  });

  it('allows retry after a script fails', async () => {
    delete window.google;
    const preparing = sdk.prepareGoogleDrivePicker(CONFIG);
    const assertion = expect(preparing).rejects.toThrow('Check your connection');
    document.querySelector('script').dispatchEvent(new Event('error'));
    await assertion;
    expect(document.querySelectorAll('script')).toHaveLength(0);
    installSdk();
    await expect(sdk.prepareGoogleDrivePicker(CONFIG)).resolves.toBeUndefined();
  });

  it('bounds script loading when the network stalls', async () => {
    vi.useFakeTimers();
    delete window.google;
    const preparing = sdk.prepareGoogleDrivePicker(CONFIG);
    const assertion = expect(preparing).rejects.toThrow('Check your connection');
    await vi.advanceTimersByTimeAsync(15000);
    await assertion;
  });

  it('allows retry after the picker module times out', async () => {
    delete window.google.picker;
    const preparing = sdk.prepareGoogleDrivePicker(CONFIG);
    const assertion = expect(preparing).rejects.toThrow('took too long');
    await Promise.resolve();
    await Promise.resolve();
    window.gapi.load.mock.calls[0][1].ontimeout();
    await assertion;
    installSdk();
    await expect(sdk.prepareGoogleDrivePicker(CONFIG)).resolves.toBeUndefined();
  });
});
