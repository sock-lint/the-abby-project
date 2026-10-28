import { startTransition, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useApi';
import { getToken } from '../api/client';
import { setRequestSpace } from '../api/space';
import { usePwaStatus } from '../pwa/pwaStatus.context';
import { SpaceContext } from './spaceContext';
import { notificationLinkSpace } from '../utils/notificationLinks';

function readPreferences(key) {
  try { return JSON.parse(sessionStorage.getItem(key)) || {}; } catch { return {}; }
}

function routePathname(pathname) {
  // Match the router's decoded segments without treating an encoded slash
  // inside one segment as a new route separator.
  try { return pathname.split('/').map(part => decodeURIComponent(part).replaceAll('/', '%2F')).join('/').toLowerCase(); }
  catch { return pathname.toLowerCase(); }
}

function isFamilyOnlyPath(pathname) {
  return /^\/(family|manage|activity|codex)(\/|$)/.test(routePathname(pathname));
}

function consumeSpaceHint(path) {
  if (!notificationLinkSpace(path)) return path;
  const parsed = new URL(path, window.location.origin);
  parsed.searchParams.delete('space');
  return `${parsed.pathname}${parsed.search}${parsed.hash}`;
}

function safePath(path, personal = false) {
  if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//')) return '/';
  const parsed = new URL(path, window.location.origin);
  if (/^\/(api|oauth|login|signup)(\/|$)/.test(routePathname(parsed.pathname))) return '/';
  if (personal && isFamilyOnlyPath(parsed.pathname)) return '/';
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
  const [initialPreferences] = useState(() => readPreferences(storageKey));
  const preferences = useRef(initialPreferences);
  const [space, setSpace] = useState(() => isParentAccount
    ? notificationLinkSpace(`${location.pathname}${location.search}`)
      ?? (initialPreferences.space === 'personal' ? 'personal' : 'family') : 'personal');
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
    if (space === 'personal' && isFamilyOnlyPath(location.pathname)) return;
    const path = `${location.pathname}${location.search}${location.hash}`;
    // A hint selects the launch/notification destination once. Keeping it in
    // history could otherwise override a later explicit switch after Back and
    // reload. This only replaces the URL; it never bypasses switch guards.
    const rememberedPath = isParentAccount ? consumeSpaceHint(path) : path;
    preferences.current[space] = safePath(rememberedPath, space === 'personal');
    if (isParentAccount) {
      preferences.current.space = space;
      try { sessionStorage.setItem(storageKey, JSON.stringify(preferences.current)); } catch { /* Optional preference. */ }
    }
  }, [location, space, isParentAccount, storageKey]);

  useEffect(() => {
    if (!isParentAccount || (space === 'personal' && isFamilyOnlyPath(location.pathname))) return;
    const path = `${location.pathname}${location.search}${location.hash}`;
    const consumed = consumeSpaceHint(path);
    // Router history listeners are installed in layout effects. Replace only
    // after they are ready, so both the URL and router location lose the hint.
    if (consumed !== path) navigate(consumed, { replace: true });
  }, [isParentAccount, location, navigate, space]);

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
  }, [isParentAccount, updateBlocked, storageKey, navigate]);

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
