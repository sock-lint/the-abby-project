import { api } from './client';

// Parent workspaces filter only complete, current-family lists. Request page
// numbers on a fixed endpoint rather than following server-advertised URLs.
// A bound or failed page is an error, never a silently incomplete family list.
async function familyList(path, signal, fetchFirstPage) {
  const rows = new Map();
  for (let page = 1; page <= 100; page += 1) {
    const separator = path.includes('?') ? '&' : '?';
    const response = page === 1 && fetchFirstPage
      ? await fetchFirstPage(signal)
      : await api.get(page === 1 ? path : `${path}${separator}page=${page}`, { signal });
    const entries = Array.isArray(response) ? response : response?.results;
    if (!Array.isArray(entries)) throw new Error('Could not load every family record. Try again.');
    for (const entry of entries) rows.set(entry.id, entry);
    if (Array.isArray(response) || !response.next) return [...rows.values()];
  }
  throw new Error('Could not load every family record. Try again.');
}

export const getFamilyChildren = (signal, fetchFirstPage) => familyList('/children/', signal, fetchFirstPage);
export const getFamilyChores = (signal) => familyList('/chores/', signal);
export const getFamilyChoreProposals = (signal) => familyList('/chores/?pending=true', signal);
export const getFamilyChoreCompletions = (signal) => familyList('/chore-completions/?status=pending', signal);
export const getFamilyHabits = (signal) => familyList('/habits/', signal);
export const getFamilyHabitProposals = (signal) => familyList('/habits/?pending=true', signal);
