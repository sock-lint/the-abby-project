const LINK_ORIGIN = 'https://abby.invalid';

export function relativeNotificationUrl(target) {
  if (typeof target !== 'string' || !target.startsWith('/') || target.startsWith('//')) return null;
  try {
    const url = new URL(target, LINK_ORIGIN);
    return url.origin === LINK_ORIGIN ? url : null;
  } catch { return null; }
}

// These presentation hints select an existing parent workspace. They never
// select a user or authorize data; account and family checks remain separate.
export function notificationLinkSpace(target) {
  const url = relativeNotificationUrl(target);
  if (!url) return null;
  const spaces = url.searchParams.getAll('space');
  if (url.pathname === '/family' && spaces.length === 0) return 'family';
  if (spaces.length !== 1) return null;
  const tabs = url.searchParams.getAll('tab');
  const tab = tabs.length === 1 ? tabs[0] : null;
  if (spaces[0] === 'personal') {
    if (['/quests', '/bestiary', '/chores'].includes(url.pathname)) return 'personal';
    const projectId = /^\/projects\/([1-9]\d*)$/.exec(url.pathname)?.[1];
    if (projectId && Number.isSafeInteger(Number(projectId))) return 'personal';
    if (url.pathname === '/chronicle' && tab === 'journal') return 'personal';
    if (url.pathname === '/treasury' && tab === 'hoards') return 'personal';
  }
  if (spaces[0] === 'family') {
    if (url.pathname === '/family') return 'family';
    const children = url.searchParams.getAll('child');
    if (url.pathname === '/chronicle' && ['journal', 'grades'].includes(tab)
      && children.length === 1 && /^[1-9]\d*$/.test(children[0])
      && Number.isSafeInteger(Number(children[0]))) return 'family';
  }
  return null;
}
