import { api } from './client';

// Auth
export const login = (username, password) =>
  api.post('/auth/', { action: 'login', username, password });
export const logout = () => api.post('/auth/', { action: 'logout' });
export const getMe = () => api.get('/auth/me/');

// Dashboard
export const getDashboard = () => api.get('/dashboard/');

// Projects
export const getProjects = () => api.get('/projects/');
export const getProject = (id) => api.get(`/projects/${id}/`);
export const createProject = (data) => api.post('/projects/', data);
export const updateProject = (id, data) => api.patch(`/projects/${id}/`, data);
export const submitProject = (id) => api.post(`/projects/${id}/submit/`);
export const approveProject = (id) => api.post(`/projects/${id}/approve/`);
export const requestChanges = (id, notes) =>
  api.post(`/projects/${id}/request-changes/`, { notes });

// Milestones
export const getMilestones = (projectId) =>
  api.get(`/projects/${projectId}/milestones/`);
export const createMilestone = (projectId, data) =>
  api.post(`/projects/${projectId}/milestones/`, data);
export const completeMilestone = (projectId, id) =>
  api.post(`/projects/${projectId}/milestones/${id}/complete/`);

// Materials
export const getMaterials = (projectId) =>
  api.get(`/projects/${projectId}/materials/`);
export const createMaterial = (projectId, data) =>
  api.post(`/projects/${projectId}/materials/`, data);
export const markPurchased = (projectId, id, actual_cost) =>
  api.post(`/projects/${projectId}/materials/${id}/mark-purchased/`, { actual_cost });

// Clock
export const getClockStatus = () => api.get('/clock/');
export const clockIn = (project_id) =>
  api.post('/clock/', { action: 'in', project_id });
export const clockOut = (notes) =>
  api.post('/clock/', { action: 'out', notes });

// Time Entries
export const getTimeEntries = () => api.get('/time-entries/');

// Timecards
export const getTimecards = () => api.get('/timecards/');
export const getTimecard = (id) => api.get(`/timecards/${id}/`);
export const approveTimecard = (id, notes) =>
  api.post(`/timecards/${id}/approve/`, { notes });
export const disputeTimecard = (id) => api.post(`/timecards/${id}/dispute/`);
export const markTimecardPaid = (id, amount) =>
  api.post(`/timecards/${id}/mark-paid/`, { amount });

// Payments
export const getBalance = () => api.get('/balance/');
export const getPayments = () => api.get('/payments/');
export const recordPayout = (user_id, amount) =>
  api.post('/payments/payout/', { user_id, amount });

// Achievements
export const getBadges = () => api.get('/badges/');
export const getEarnedBadges = () => api.get('/badges/earned/');
export const getSkillTree = (categoryId) => api.get(`/skills/tree/${categoryId}/`);
export const getSkillProgress = () => api.get('/skill-progress/');
export const getAchievementsSummary = () => api.get('/achievements/summary/');

// Portfolio
export const getPortfolio = () => api.get('/portfolio/');
export const getPhotos = () => api.get('/photos/');

// Categories
export const getCategories = () => api.get('/categories/');
