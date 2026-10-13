import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { getGoogleDriveConfig, getGoogleDriveSources, uploadAbbyFileToGoogleDrive } from '../api';
import { AUTH_CHANGED_EVENT, getToken } from '../api/client';
import { STORAGE_KEYS } from '../constants/storage';
import { authorizeGoogleDrive, prepareGoogleDriveAuthorization } from '../utils/googleDrivePicker';
import Button from './Button';
import ErrorAlert from './ErrorAlert';
import Loader from './Loader';
import { SelectField } from './form';

const CATEGORIES = [
  ['ingestion_pdf', 'Imported PDFs'],
  ['project_photo', 'Project photos'],
  ['homework_proof', 'Approved homework photos'],
  ['creation_photo', 'Creation photos'],
];
const EMPTY_PAGE = { count: 0, next: null, previous: null, results: [] };

export default function SaveAbbyFileToDrive({ onSaved, onBusyChange, disabled = false }) {
  const [sessionToken] = useState(getToken);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [sourceType, setSourceType] = useState('ingestion_pdf');
  const [page, setPage] = useState(1);
  const [listing, setListing] = useState(EMPTY_PAGE);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState('');
  const [config, setConfig] = useState(null);
  const [preparing, setPreparing] = useState(true);
  const [configError, setConfigError] = useState('');
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saved, setSaved] = useState(null);
  const [notice, setNotice] = useState('');
  const radioName = useId();
  const mounted = useRef(false);
  const operation = useRef(null);
  const sourceRequest = useRef(null);
  const configGeneration = useRef(0);
  const busyChangeRef = useRef(onBusyChange);
  useEffect(() => { busyChangeRef.current = onBusyChange; }, [onBusyChange]);
  const current = useCallback((controller) => (
    mounted.current && getToken() === sessionToken && !controller?.signal.aborted
  ), [sessionToken]);

  useEffect(() => {
    mounted.current = true;
    const sessionChanged = (event) => {
      if (event.type === 'storage' && event.key !== null && event.key !== STORAGE_KEYS.AUTH_TOKEN) return;
      if (getToken() === sessionToken) return;
      operation.current?.abort();
      sourceRequest.current?.abort();
      configGeneration.current += 1;
      setSessionEnded(true);
      setSelected(null);
      setListing(EMPTY_PAGE);
      setSaved(null);
      setConfig(null);
      setBusy(false);
      busyChangeRef.current?.(false);
    };
    window.addEventListener(AUTH_CHANGED_EVENT, sessionChanged);
    window.addEventListener('storage', sessionChanged);
    return () => {
      mounted.current = false;
      configGeneration.current += 1;
      operation.current?.abort();
      sourceRequest.current?.abort();
      busyChangeRef.current?.(false);
      window.removeEventListener(AUTH_CHANGED_EVENT, sessionChanged);
      window.removeEventListener('storage', sessionChanged);
    };
  }, [sessionToken]);

  const prepare = useCallback(async () => {
    const generation = ++configGeneration.current;
    setPreparing(true);
    setConfigError('');
    try {
      const next = await getGoogleDriveConfig();
      if (!current() || generation !== configGeneration.current) return;
      await prepareGoogleDriveAuthorization(next);
      if (current() && generation === configGeneration.current) setConfig(next);
    } catch (error) {
      if (current() && generation === configGeneration.current) setConfigError(error.message);
    } finally {
      if (current() && generation === configGeneration.current) setPreparing(false);
    }
  }, [current]);
  useEffect(() => { void prepare(); }, [prepare]);

  const loadSources = useCallback(async () => {
    sourceRequest.current?.abort();
    const controller = new AbortController();
    sourceRequest.current = controller;
    setLoading(true);
    setSelected(null);
    setListing(EMPTY_PAGE);
    setListError('');
    try {
      const result = await getGoogleDriveSources(sourceType, page, { signal: controller.signal, token: sessionToken });
      if (current(controller)) setListing(result);
    } catch (error) {
      if (current(controller)) setListError(error.message);
    } finally {
      if (current(controller)) setLoading(false);
    }
  }, [current, sourceType, page, sessionToken]);
  useEffect(() => {
    if (!sessionEnded) void loadSources();
    return () => sourceRequest.current?.abort();
  }, [loadSources, sessionEnded]);

  const save = async () => {
    if (!selected || !config || operation.current || disabled || !current()) return;
    const source = selected;
    const controller = new AbortController();
    operation.current = controller;
    let uploadStarted = false;
    setBusy(true);
    setSaveError('');
    setNotice('');
    setSaved(null);
    busyChangeRef.current?.(true);
    try {
      // Nothing is awaited before opening Google's popup: this is the click.
      const accessToken = await authorizeGoogleDrive(config, { signal: controller.signal });
      if (!accessToken || !current(controller)) return;
      uploadStarted = true;
      const resource = await uploadAbbyFileToGoogleDrive({
        source_type: source.source_type, source_id: source.source_id, access_token: accessToken,
      }, { signal: controller.signal, token: sessionToken });
      if (!current(controller)) return;
      setSaved(resource);
      onSaved?.(resource);
    } catch (error) {
      if (current(controller)) setSaveError(uploadStarted && (error.offline || !error.status || error.status >= 500)
        ? 'Abby could not confirm the copy. Check My Drive before saving again; another save creates another copy.'
        : error.message);
    } finally {
      if (mounted.current && getToken() === sessionToken && controller.signal.aborted && uploadStarted) {
        setNotice('Stopped waiting for the save. Check My Drive before saving again; the copy may already be there.');
      }
      if (operation.current === controller) operation.current = null;
      if (mounted.current) setBusy(false);
      busyChangeRef.current?.(false);
    }
  };

  if (sessionEnded) return <ErrorAlert message="Your account changed. Close this panel and reopen it to choose a file." />;
  return (
    <div role="region" aria-label="Save a file from Abby" className="space-y-3">
      <p className="text-body text-ink-secondary">
        Save one PDF or photo already in Abby to the top level of My Drive in the Google account you choose.
        Each save creates a new copy. The original stays in Abby, and Drive sharing stays under your control.
      </p>
      <SelectField label="File category" value={sourceType} disabled={busy || disabled} onChange={(event) => {
        setSourceType(event.target.value); setPage(1); setSelected(null); setSaved(null); setSaveError(''); setNotice('');
      }}>
        {CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </SelectField>
      <ErrorAlert message={listError} onRetry={loadSources} />
      {loading ? <Loader delayMs={0} /> : !listError && (listing.results.length ? (
        <fieldset className="space-y-2" disabled={busy || disabled}>
          <legend className="text-body font-semibold text-ink-primary">Choose one file</legend>
          {listing.results.map((source) => (
            <label key={`${source.source_type}-${source.source_id}`} className="flex items-center gap-3 min-h-11 p-3 rounded-lg border border-ink-page-shadow text-body text-ink-primary">
              <input type="radio" name={radioName} aria-label={`${source.title}${source.context ? ` ${source.context}` : ''}`} value={source.source_id} checked={selected?.source_id === source.source_id} onChange={() => {
                setSelected(source); setSaved(null); setSaveError(''); setNotice('');
              }} />
              <span className="min-w-0 break-words">
                <span className="block font-semibold">{source.title}</span>
                {source.context && <span className="block text-caption text-ink-secondary">{source.context}</span>}
              </span>
            </label>
          ))}
        </fieldset>
      ) : <p role="status" className="text-body text-ink-secondary">No files in this category yet.</p>)}
      {!loading && !listError && listing.count > 0 && (
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <Button variant="secondary" size="sm" disabled={busy || disabled || !listing.previous} onClick={() => setPage(page - 1)}>Previous files</Button>
          <span className="text-caption text-ink-secondary">Page {page} · {listing.count} {listing.count === 1 ? 'file' : 'files'}</span>
          <Button variant="secondary" size="sm" disabled={busy || disabled || !listing.next} onClick={() => setPage(page + 1)}>Next files</Button>
        </div>
      )}
      <ErrorAlert message={configError} onRetry={!busy && !disabled ? prepare : undefined} />
      <ErrorAlert message={saveError} />
      {notice && <p role="status" className="text-body text-ink-secondary">{notice}</p>}
      {saved && <p role="status" className="text-body text-ink-primary">
        Saved {saved.title} to My Drive. <a href={saved.url} target="_blank" rel="noopener noreferrer" className="underline text-sheikah-teal-deep">Open in Google Drive</a>
      </p>}
      <div className="flex items-center gap-2 flex-wrap">
        <Button disabled={disabled || loading || preparing || busy || !selected || !config} onClick={save} aria-busy={busy}>
          {busy ? 'Saving to Google Drive…' : 'Save to Google Drive'}
        </Button>
        {busy && <Button variant="secondary" onClick={() => operation.current?.abort()}>Stop waiting</Button>}
      </div>
    </div>
  );
}
