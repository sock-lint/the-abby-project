import { api } from './client';

const roots = {
  content: '/rpg/content-workbench/drafts/',
  editorial: '/rpg/editorial/drafts/',
  experiment: '/rpg/progression-lab/experiments/',
};
const root = (kind) => {
  if (!Object.hasOwn(roots, kind)) throw new TypeError('Unknown authoring kind.');
  return roots[kind];
};

export const setAuthoringArchived = (kind, id, data, options) =>
  api.post(`${root(kind)}${encodeURIComponent(id)}/archive/`, data, options);
export const listAuthoringHistory = (kind, { includeArchived = false, after, limit = 20 } = {}, options) => {
  const query = new URLSearchParams({ include_archived: String(includeArchived), limit: String(limit) });
  if (after) query.set('after', after);
  return api.get(`${root(kind)}?${query}`, options);
};
