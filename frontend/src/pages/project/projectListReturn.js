const LIST_PATH = '/quests';
const STATUSES = new Set(['draft', 'in_progress', 'in_review', 'completed']);
const TYPES = new Set(['required', 'bounty']);

// Return navigation owns this route and these filters. Never copy a caller's
// arbitrary destination, credential/query fields, origin, or fragment.
export function projectListSearch(search) {
  const source = new URLSearchParams(typeof search === 'string' ? search : '');
  const result = new URLSearchParams({ tab: 'ventures' });
  if (STATUSES.has(source.get('status'))) result.set('status', source.get('status'));
  if (TYPES.has(source.get('type'))) result.set('type', source.get('type'));
  const child = source.get('child');
  if (child === 'unassigned' || /^[1-9]\d{0,18}$/.test(child || '')) result.set('child', child);
  const query = source.get('q')?.slice(0, 256);
  if (query) result.set('q', query);
  return `?${result}`;
}

function safeScroll(value) {
  return Number.isFinite(value) && value >= 0 && value <= 1_000_000 ? Math.floor(value) : 0;
}

export function captureProjectListReturn(search, userId, scrollY) {
  return { search: projectListSearch(search), userId, scrollY: safeScroll(scrollY) };
}

export function projectListDestination(saved, userId) {
  const valid = userId != null && saved?.userId === userId;
  return {
    to: `${LIST_PATH}${projectListSearch(valid ? saved.search : '')}`,
    state: valid ? { projectListScroll: { userId, top: safeScroll(saved.scrollY) } } : undefined,
  };
}
