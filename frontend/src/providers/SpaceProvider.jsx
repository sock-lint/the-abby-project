import { startTransition, useCallback, useLayoutEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useApi';
import { getToken } from '../api/client';
import { setRequestSpace } from '../api/space';
import { usePwaStatus } from '../pwa/pwaStatus.context';
import { SpaceContext } from './spaceContext';

function readPreferences(key) {
  try { return JSON.parse(sessionStorage.getItem(key)) || {}; } catch { return {}; }
}

function safePath(path, personal = false) {
  if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')) return '/';
  const parsed = new URL(path, window.location.origin);
  if (/^\/(api|oauth|login|signup)(\/|$)/.test(parsed.pathname)) return '/';
  if (personal && /^\/(family|manage|activity|codex)(\/|$)/.test(parsed.pathname)) return '/';
  if (personal) parsed.searchParams.delete('child');
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}

export default function SpaceProvider({ children }) {
  const { user } = useAuth();
  const token = getToken();
  const accountKey = `${user?.id}:${user?.family?.id}:${token}`;
  return <AccountSpaces key={accountKey} user={user} token={token}>{children}</AccountSpaces>;
}

function AccountSpaces({ user, token, children }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { updateBlocked } = usePwaStatus();
  const isParentAccount = user?.role === 'parent';
  const storageKey = `abby:spaces:${user?.family?.id}:${user?.id}`;
  const preferences = useRef(readPreferences(storageKey));
  const [space, setSpace] = useState(() => isParentAccount
    ? (preferences.current.space === 'personal' ? 'personal' : 'family') : 'personal');
  const [revision, setRevision] = useState(0);

  // Every new workspace mounts with its own fetches and forms. Layout effects
  // run before those requests, so no new component can use the previous scope.
  useLayoutEffect(() => {
    setRequestSpace(isParentAccount ? space : 'family', token);
    return () => setRequestSpace('family', '');
  }, [isParentAccount, space, token]);

  // A Family-only link can arrive before its route guard changes space.
  // Preserve the last actual personal page instead of saving that transient
  // Family URL as the page My space should restore.
  useLayoutEffect(() => {
    if (space === 'personal' && /^\/(family|manage|activity|codex)(\/|$)/.test(location.pathname)) return;
    preferences.current[space] = safePath(`${location.pathname}${location.search}${location.hash}`, space === 'personal');
  }, [location, space]);

  const switchSpace = useCallback((next, destination) => {
    if (!isParentAccount || !['family', 'personal'].includes(next) || updateBlocked) return false;
    const selectedPath = typeof destination === 'string' ? destination : destination?.to;
    const path = safePath(selectedPath || preferences.current[next] || '/', next === 'personal');
    preferences.current.space = next;
    try { sessionStorage.setItem(storageKey, JSON.stringify(preferences.current)); } catch { /* Optional preference. */ }
    // Router location updates use a transition. Commit the space in that same
    // transition so a Family-only route cannot briefly mount in My space and
    // immediately redirect back. The layout effect binds transport at commit.
    startTransition(() => {
      setSpace(next);
      setRevision(value => value + 1);
      navigate(path, { replace: true });
    });
    return true;
  }, [isParentAccount, updateBlocked, location, space, storageKey, token, navigate]);

  return (
    <SpaceContext.Provider value={{
      space, isParentAccount, isPersonalSpace: space === 'personal',
      isFamilySpace: isParentAccount && space === 'family',
      switchSpace, switchBlocked: updateBlocked,
    }}>
      <div key={`${space}:${revision}`} className="contents">{children}</div>
    </SpaceContext.Provider>
  );
}
