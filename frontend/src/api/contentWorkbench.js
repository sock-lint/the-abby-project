import { api } from './client';

const root = '/rpg/content-workbench/';
const draftUrl = (id) => `${root}drafts/${encodeURIComponent(id)}/`;

export const getContentWorkbench = (options) => api.get(root, options);
export const createContentDraft = (data, options) => api.post(`${root}drafts/`, data, options);
export const getContentDraft = (id, options) => api.get(draftUrl(id), options);
export const updateContentDraft = (id, data, options) => api.patch(draftUrl(id), data, options);
export const previewContentDraft = (id, data, options) => api.post(`${draftUrl(id)}preview/`, data, options);
export const simulateContentDraft = (id, data, options) => api.post(`${draftUrl(id)}simulate/`, data, options);
export const publishContentDraft = (id, data, options) => api.post(`${draftUrl(id)}publish/`, data, options);
