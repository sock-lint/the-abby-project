import { useCallback, useEffect, useRef, useState } from 'react';
import { getGoogleDriveConfig } from '../api';
import { AUTH_CHANGED_EVENT, getToken } from '../api/client';
import { STORAGE_KEYS } from '../constants/storage';
import { pickGoogleDriveFile, prepareGoogleDrivePicker } from '../utils/googleDrivePicker';
import Button from './Button';
import ErrorAlert from './ErrorAlert';

export default function GoogleDrivePickerButton({
  onPick, pdfOnly = false, disabled = false, children = 'Choose from Google Drive', onOpenChange,
}) {
  const [config, setConfig] = useState(null);
  const [preparing, setPreparing] = useState(true);
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState('');
  const mounted = useRef(false);
  const generation = useRef(0);
  const operation = useRef(null);
  const openChangeRef = useRef(onOpenChange);
  useEffect(() => { openChangeRef.current = onOpenChange; }, [onOpenChange]);

  const prepare = useCallback(async () => {
    const request = ++generation.current;
    const credential = getToken();
    setPreparing(true);
    setConfig(null);
    setError('');
    try {
      const next = await getGoogleDriveConfig();
      if (!mounted.current || request !== generation.current || getToken() !== credential) return;
      await prepareGoogleDrivePicker(next);
      if (mounted.current && request === generation.current && getToken() === credential) setConfig(next);
    } catch (err) {
      if (mounted.current && request === generation.current && getToken() === credential) setError(err.message);
    } finally {
      if (mounted.current && request === generation.current && getToken() === credential) setPreparing(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void prepare();
    const sessionChanged = (event) => {
      if (event.type === 'storage' && event.key !== null && event.key !== STORAGE_KEYS.AUTH_TOKEN) return;
      operation.current?.abort();
      void prepare();
    };
    window.addEventListener(AUTH_CHANGED_EVENT, sessionChanged);
    window.addEventListener('storage', sessionChanged);
    return () => {
      mounted.current = false;
      generation.current += 1;
      operation.current?.abort();
      openChangeRef.current?.(false);
      window.removeEventListener(AUTH_CHANGED_EVENT, sessionChanged);
      window.removeEventListener('storage', sessionChanged);
    };
  }, [prepare]);

  const pick = async () => {
    if (!config || operation.current || disabled) return;
    const controller = new AbortController();
    operation.current = controller;
    const credential = getToken();
    const current = () => mounted.current && !controller.signal.aborted && getToken() === credential;
    setError('');
    setPicking(true);
    openChangeRef.current?.(true);
    try {
      const selection = await pickGoogleDriveFile(config, { pdfOnly, signal: controller.signal });
      if (selection && current()) await onPick(selection);
    } catch (err) {
      if (current()) setError(err.message);
    } finally {
      if (operation.current === controller) operation.current = null;
      if (mounted.current) setPicking(false);
      openChangeRef.current?.(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button variant="secondary" disabled={disabled || preparing || !config || picking} onClick={pick} aria-busy={preparing || picking}>
        {preparing ? 'Preparing Google Drive…' : picking ? 'Choosing from Google Drive…' : children}
      </Button>
      <ErrorAlert message={error} onRetry={!preparing && !picking && !disabled ? (config ? pick : prepare) : undefined} />
    </div>
  );
}
