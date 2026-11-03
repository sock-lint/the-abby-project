import { useCallback, useEffect, useRef, useState } from 'react';
import { getEggDiscoveries, logEggDiscoveryPractice, pauseEggDiscovery, selectEggDiscovery } from '../api/eggDiscoveries';
import { getToken } from '../api/client';
import { useApi, friendlyErrorMessage } from './useApi';
import { useRole } from './useRole';
import { useSpace } from './useSpace';
import { usePulse } from '../providers/pulseContext';
import { createRequestId } from '../utils/requestId';
import { fieldErrors } from '../utils/api';

export const EGG_DISCOVERIES_CHANGED = 'abby:egg-discoveries-changed';
const DISABLED = { enabled: false, offers: [], discoveries: [], active_id: null };

export default function useEggDiscoveries({ refreshKey } = {}) {
  const { user } = useRole();
  const { space, isFamilySpace } = useSpace();
  const { pulse } = usePulse();
  const token = getToken();
  const allowed = Boolean(user?.id && token && !isFamilySpace);
  const scope = `${user?.id}:${user?.family?.id}:${user?.role}:${token}:${space}`;
  const read = useCallback(async (signal) => ({
    ...(allowed ? await getEggDiscoveries({ signal, token, space }) : DISABLED),
    _eggScope: scope,
  }), [allowed, token, space, scope]);
  const result = useApi(read, [scope, allowed, refreshKey, pulse]);
  const { reload, setData } = result;
  const mounted = useRef(false);
  const latestScope = useRef(scope);
  const inFlight = useRef(null);
  const pending = useRef(null);
  const [action, setAction] = useState(null);
  useEffect(() => {
    mounted.current = true;
    latestScope.current = scope;
    return () => { mounted.current = false; };
  }, [scope]);
  useEffect(() => {
    const update = () => reload();
    window.addEventListener(EGG_DISCOVERIES_CHANGED, update);
    return () => window.removeEventListener(EGG_DISCOVERIES_CHANGED, update);
  }, [reload]);

  const mutate = async (kind, body) => {
    if (!allowed || inFlight.current?.scope === scope) return null;
    const signature = JSON.stringify([kind, body]);
    // Preserve a UUID only for the exact same intent in this session. A new
    // account, changed payload, or confirmed receipt gets a new identity.
    if (pending.current?.scope !== scope || pending.current.signature !== signature) {
      pending.current = { scope, kind, body, signature, id: createRequestId() };
    }
    const request = pending.current;
    const current = () => mounted.current && latestScope.current === scope && getToken() === token;
    inFlight.current = request;
    setAction({ scope, busy: true, error: '', errors: {}, uncertain: false });
    try {
      const payload = { ...request.body, client_request_id: request.id };
      const options = { token, space };
      const response = kind === 'select' ? await selectEggDiscovery(payload, options)
        : kind === 'pause' ? await pauseEggDiscovery(request.body.id, { client_request_id: request.id }, options)
          : await logEggDiscoveryPractice(payload, options);
      if (!current()) return null;
      pending.current = null;
      setAction(null);
      setData({ ...response, _eggScope: scope });
      window.dispatchEvent(new Event(EGG_DISCOVERIES_CHANGED));
      return response;
    } catch (error) {
      if (!current()) return null;
      const definite = error.status >= 400 && error.status < 500;
      if (definite) pending.current = null;
      const errors = fieldErrors(error);
      setAction({ scope, busy: false, error: Object.keys(errors).length ? 'Check the highlighted fields.' : friendlyErrorMessage(error), errors, uncertain: !definite });
      if (error.status === 409) reload();
      return null;
    } finally {
      if (inFlight.current === request) inFlight.current = null;
    }
  };
  const data = result.data?._eggScope === scope ? result.data : null;
  const state = action?.scope === scope ? action : null;
  return {
    data, allowed, enabled: data?.enabled === true,
    loading: allowed && (result.loading || (!data && !result.error)),
    refreshing: result.refreshing, error: allowed ? result.error : null, reload,
    busy: state?.busy === true, uncertain: state?.uncertain === true,
    actionError: state?.error || '', fieldErrors: state?.errors || {},
    retry: () => pending.current?.scope === scope && mutate(pending.current.kind, pending.current.body),
    select: (key) => mutate('select', { offer_key: key }),
    pause: (id) => mutate('pause', { id }),
    logPractice: (body) => mutate('practice', body),
  };
}
