// Drive credentials are deliberately confined to the current picker operation.
// The saved resource is resolved by Django; Picker titles/URLs are not trusted.
export const GOOGLE_DRIVE_SCOPE = 'https://www.googleapis.com/auth/drive.file';
const GIS_URL = 'https://accounts.google.com/gsi/client';
const GAPI_URL = 'https://apis.google.com/js/api.js';
const LOAD_TIMEOUT = 15000;
const scriptLoads = new Map();
let pickerLoad;

function loadScript(src, ready) {
  if (ready()) return Promise.resolve();
  if (scriptLoads.has(src)) return scriptLoads.get(src);
  const promise = new Promise((resolve, reject) => {
    let script = document.querySelector(`script[src="${src}"]`);
    const created = !script;
    if (!script) {
      script = document.createElement('script');
      script.src = src;
      script.async = true;
    }
    const finish = (error) => {
      clearTimeout(timeout);
      script.removeEventListener('load', onLoad);
      script.removeEventListener('error', onError);
      if (error) {
        if (created) script.remove();
        reject(error);
      } else resolve();
    };
    const onLoad = () => finish(ready() ? null : new Error('Google Drive could not load. Please try again.'));
    const onError = () => finish(new Error('Google Drive could not load. Check your connection and try again.'));
    const timeout = setTimeout(onError, LOAD_TIMEOUT);
    script.addEventListener('load', onLoad);
    script.addEventListener('error', onError);
    if (created) document.head.appendChild(script);
  });
  scriptLoads.set(src, promise);
  promise.catch(() => { if (scriptLoads.get(src) === promise) scriptLoads.delete(src); });
  return promise;
}

function loadPicker() {
  if (window.google?.picker?.PickerBuilder) return Promise.resolve();
  if (pickerLoad) return pickerLoad;
  const promise = new Promise((resolve, reject) => {
    window.gapi.load('picker', {
      callback: () => {
        if (window.google?.picker?.PickerBuilder) resolve();
        else reject(new Error('Google Drive picker could not load. Please try again.'));
      },
      onerror: () => reject(new Error('Google Drive picker could not load. Please try again.')),
      timeout: LOAD_TIMEOUT,
      ontimeout: () => reject(new Error('Google Drive picker took too long to load. Please try again.')),
    });
  });
  pickerLoad = promise;
  promise.catch(() => { if (pickerLoad === promise) pickerLoad = undefined; });
  return promise;
}

/** Prepare SDKs before enabling the button, preserving the OAuth popup gesture. */
export async function prepareGoogleDrivePicker(config) {
  if (!config?.configured || !config.client_id || !config.api_key || !config.app_id) {
    throw new Error('Google Drive is not available yet. You can still paste a link or upload a PDF.');
  }
  await Promise.all([
    loadScript(GIS_URL, () => !!window.google?.accounts?.oauth2?.initTokenClient),
    loadScript(GAPI_URL, () => !!window.gapi?.load),
  ]);
  await loadPicker();
}

/** Call directly from a click after preparation. Aborting disposes the picker. */
export function pickGoogleDriveFile(config, { pdfOnly = false, allowUpload = false, signal } = {}) {
  return new Promise((resolve, reject) => {
    let settled = false;
    let picker;
    let accessToken;
    const finish = (value, error) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener('abort', cancel);
      try { picker?.dispose(); } catch { /* Still settle if Google's cleanup fails. */ }
      accessToken = undefined;
      if (error) reject(error);
      else resolve(value);
    };
    const cancel = () => finish(null);
    if (signal?.aborted) { cancel(); return; }
    signal?.addEventListener('abort', cancel, { once: true });
    try {
      const oauth = window.google.accounts.oauth2;
      const tokenClient = oauth.initTokenClient({
        client_id: config.client_id,
        scope: GOOGLE_DRIVE_SCOPE,
        include_granted_scopes: false,
        callback: (response) => {
          if (settled || picker) return;
          try {
            if (response?.error || !response?.access_token) {
              finish(null, new Error('Google Drive access was not granted. Try again and allow access to the files you select.'));
              return;
            }
            if (!oauth.hasGrantedAllScopes(response, GOOGLE_DRIVE_SCOPE)) {
              finish(null, new Error('Allow access to the Google Drive files you select, then try again.'));
              return;
            }
            accessToken = response.access_token;
            const api = window.google.picker;
            const view = new api.DocsView(api.ViewId.DOCS).setIncludeFolders(true).setSelectFolderEnabled(false);
            if (pdfOnly) view.setMimeTypes('application/pdf');
            const builder = new api.PickerBuilder().addView(view);
            // UploadView accepts all file types. Keep the PDF import chooser
            // limited to existing PDFs instead of offering unfiltered uploads.
            if (allowUpload && !pdfOnly) builder.addView(new api.DocsUploadView().setIncludeFolders(true));
            picker = builder
              .setOAuthToken(accessToken)
              .setDeveloperKey(config.api_key)
              .setAppId(config.app_id)
              .setOrigin(window.location.origin)
              .setTitle(pdfOnly ? 'Choose a school or project PDF' : allowUpload ? 'Choose or upload a project resource' : 'Choose a project resource')
              .setCallback((data) => {
                if (settled) return;
                const action = data?.[api.Response.ACTION];
                if (action === api.Action.CANCEL) { cancel(); return; }
                if (action === api.Action.ERROR) {
                  finish(null, new Error('Google Drive could not show your files. Check your access and try again.'));
                  return;
                }
                if (action !== api.Action.PICKED) return;
                const docs = data[api.Response.DOCUMENTS];
                if (docs?.length > 1) {
                  finish(null, new Error('Choose one file to attach to this resource. Any uploaded files stay in Google Drive.'));
                  return;
                }
                const doc = docs?.[0];
                const fileId = doc?.[api.Document.ID];
                if (!fileId || (pdfOnly && doc[api.Document.MIME_TYPE] !== 'application/pdf')) {
                  finish(null, new Error(pdfOnly ? 'Choose a PDF file from Google Drive.' : 'Google Drive did not return a file. Please try again.'));
                  return;
                }
                finish({ file_id: fileId, access_token: accessToken, ...(doc.resourceKey ? { resource_key: doc.resourceKey } : {}) });
              })
              .build();
            picker.setVisible(true);
          } catch {
            finish(null, new Error('Google Drive picker could not open. Please try again.'));
          }
        },
        error_callback: (error) => {
          if (error?.type === 'popup_closed') cancel();
          else finish(null, new Error(error?.type === 'popup_failed_to_open'
            ? 'Allow pop-ups for Abby, then try Google Drive again.'
            : 'Google Drive sign-in could not open. Please try again.'));
        },
      });
      tokenClient.requestAccessToken({ prompt: 'select_account' });
    } catch {
      finish(null, new Error('Google Drive could not start. Please try again.'));
    }
  });
}
