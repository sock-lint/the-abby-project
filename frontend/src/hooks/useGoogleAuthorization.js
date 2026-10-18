import { useEffect, useRef, useState } from 'react';
import { getToken } from '../api/client';
import { cancelGoogleAuthorization, startGoogleAuthorization } from '../auth/googleOAuth';

export default function useGoogleAuthorization({ mode, actor, forUserId } = {}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const busyRef = useRef(false);
  const mounted = useRef(true);
  const generation = useRef(0);
  const scope = `${getToken()}:${actor?.id}:${actor?.family?.id}:${forUserId}`;
  const scopeRef = useRef(scope);
  scopeRef.current = scope;
  useEffect(() => {
    mounted.current = true;
    const returned = (event) => {
      if (!event.persisted) return;
      generation.current += 1;
      cancelGoogleAuthorization();
      busyRef.current = false;
      setBusy(false);
    };
    window.addEventListener('pageshow', returned);
    return () => {
      mounted.current = false;
      generation.current += 1;
      window.removeEventListener('pageshow', returned);
    };
  }, []);

  const start = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    const request = ++generation.current;
    const token = getToken();
    const isCurrent = () => mounted.current && generation.current === request
      && scopeRef.current === scope && getToken() === token;
    let navigating = false;
    try {
      navigating = await startGoogleAuthorization({ mode, actor, forUserId, isCurrent });
    } catch (failure) {
      if (isCurrent()) setError(failure.message?.startsWith('Google authorization')
        ? failure.message : `Could not start Google ${mode === 'login' ? 'sign-in' : 'linking'}. Try again.`);
    } finally {
      if (isCurrent() && !navigating) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  };
  return { start, busy, error };
}
