import { api } from './client';

export const getEggDiscoveries = (options) => api.get('/egg-discoveries/', options);
export const selectEggDiscovery = (body, options) => api.post('/egg-discoveries/select/', body, options);
export const pauseEggDiscovery = (id, body, options) => api.post(`/egg-discoveries/${encodeURIComponent(id)}/pause/`, body, options);
export const logEggDiscoveryPractice = (body, options) => api.post('/egg-discoveries/practice/', body, options);
