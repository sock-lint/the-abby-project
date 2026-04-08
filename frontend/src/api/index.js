import { api, setToken } from './client';

// Auth
export const login = async (username, password) => {
  const data = await api.post('/auth/', { action: 'login', username, password });
  if (data && data.token) setToken(data.token);
  return data;
};
export const logout = async () => {
  try {
    await api.post('/auth/', { action: 'logout' });
  } finally {
    setToken(null);
  }
};
export const getMe = () => api.get('/auth/me/');

// Dashboard
export const getDashboard = () => api.get('/dashboard/');

// Projects
export const getProjects = () => api.get('/projects/');
export const getProject = (id) => api.get(`/projects/${id}/`);
export const createProject = (data) => api.post('/projects/', data);
export const updateProject = (id, data) => api.patch(`/projects/${id}/`, data);
export const activateProject = (id) => api.post(`/projects/${id}/activate/`);
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

// Project Ingestion (auto-pull milestones/materials from a source)
export const startIngest = ({ source_type, source_url, source_file }) => {
  if (source_type === 'pdf' && source_file) {
    const fd = new FormData();
    fd.append('source_type', 'pdf');
    fd.append('source_file', source_file);
    return api.upload('/projects/ingest/', fd);
  }
  return api.post('/projects/ingest/', { source_type, source_url });
};
export const getIngestJob = (id) => api.get(`/projects/ingest/${id}/`);
export const updateIngestJob = (id, data) =>
  api.patch(`/projects/ingest/${id}/`, data);
export const commitIngestJob = (id, overrides) =>
  api.post(`/projects/ingest/${id}/commit/`, overrides);
export const discardIngestJob = (id) => api.delete(`/projects/ingest/${id}/`);

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

// Notifications
export const getNotifications = () => api.get('/notifications/');
export const getUnreadCount = () => api.get('/notifications/unread_count/');
export const markAllRead = () => api.post('/notifications/mark_all_read/');
export const markNotificationRead = (id) => api.post(`/notifications/${id}/mark_read/`);

// Instructables
export const getInstructablesPreview = (url) =>
  api.get(`/instructables/preview/?url=${encodeURIComponent(url)}`);

// Project Templates
export const getTemplates = () => api.get('/templates/');
export const getTemplate = (id) => api.get(`/templates/${id}/`);
export const createProjectFromTemplate = (id, assigned_to_id) =>
  api.post(`/templates/${id}/create-project/`, { assigned_to_id });
export const saveProjectAsTemplate = (project_id, is_public = false) =>
  api.post('/templates/from-project/', { project_id, is_public });

// Savings Goals
export const getSavingsGoals = () => api.get('/savings-goals/');
export const createSavingsGoal = (data) => api.post('/savings-goals/', data);
export const deleteSavingsGoal = (id) => api.delete(`/savings-goals/${id}/`);
export const updateGoalAmount = (id) => api.post(`/savings-goals/${id}/update_amount/`);

// AI Suggestions
export const getProjectSuggestions = () => api.get('/projects/suggestions/');

// Collaborators
export const getCollaborators = (projectId) => api.get(`/projects/${projectId}/collaborators/`);
export const addCollaborator = (projectId, user_id, pay_split_percent) =>
  api.post(`/projects/${projectId}/collaborators/`, { user_id, pay_split_percent });

// Greenlight Import
export const importGreenlight = (user_id, csv_data) =>
  api.post('/greenlight/import/', { user_id, csv_data });
