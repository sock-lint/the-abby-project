import { api, setToken, getBlob } from './client';

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
export const updateMe = (data) => api.patch('/auth/me/', data);

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
export const updateMilestone = (projectId, id, data) =>
  api.patch(`/projects/${projectId}/milestones/${id}/`, data);
export const deleteMilestone = (projectId, id) =>
  api.delete(`/projects/${projectId}/milestones/${id}/`);
export const completeMilestone = (projectId, id) =>
  api.post(`/projects/${projectId}/milestones/${id}/complete/`);

// Steps (walkthrough instructions — no XP, no coins, no ledger)
export const getSteps = (projectId) =>
  api.get(`/projects/${projectId}/steps/`);
export const createStep = (projectId, data) =>
  api.post(`/projects/${projectId}/steps/`, data);
export const updateStep = (projectId, id, data) =>
  api.patch(`/projects/${projectId}/steps/${id}/`, data);
export const deleteStep = (projectId, id) =>
  api.delete(`/projects/${projectId}/steps/${id}/`);
export const completeStep = (projectId, id) =>
  api.post(`/projects/${projectId}/steps/${id}/complete/`);
export const uncompleteStep = (projectId, id) =>
  api.post(`/projects/${projectId}/steps/${id}/uncomplete/`);
export const reorderSteps = (projectId, order) =>
  api.post(`/projects/${projectId}/steps/reorder/`, { order });

// Resources (reference links — project-level or attached to a step)
export const getResources = (projectId, stepId) => {
  const qs = stepId === undefined ? '' : `?step=${stepId === null ? 'null' : stepId}`;
  return api.get(`/projects/${projectId}/resources/${qs}`);
};
export const createResource = (projectId, data) =>
  api.post(`/projects/${projectId}/resources/`, data);
export const updateResource = (projectId, id, data) =>
  api.patch(`/projects/${projectId}/resources/${id}/`, data);
export const deleteResource = (projectId, id) =>
  api.delete(`/projects/${projectId}/resources/${id}/`);

// Materials
export const getMaterials = (projectId) =>
  api.get(`/projects/${projectId}/materials/`);
export const createMaterial = (projectId, data) =>
  api.post(`/projects/${projectId}/materials/`, data);
export const updateMaterial = (projectId, id, data) =>
  api.patch(`/projects/${projectId}/materials/${id}/`, data);
export const deleteMaterial = (projectId, id) =>
  api.delete(`/projects/${projectId}/materials/${id}/`);
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
export const voidTimeEntry = (id) => api.post(`/time-entries/${id}/void/`);

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
export const adjustPayment = (user_id, amount, description = '') =>
  api.post('/payments/adjust/', { user_id, amount, description });

// RPG Codex — parent-only catalog of YAML-authored content
export const getItemCatalog = () => api.get('/items/catalog/');
export const getPetSpeciesCatalog = () => api.get('/pets/species/catalog/');
export const getQuestCatalog = () => api.get('/quests/catalog/');

// Achievements
export const getBadges = () => api.get('/badges/');
export const createBadge = (data) => api.post('/badges/', data);
export const updateBadge = (id, data) => api.patch(`/badges/${id}/`, data);
export const deleteBadge = (id) => api.delete(`/badges/${id}/`);
export const getEarnedBadges = () => api.get('/badges/earned/');
export const getSubjects = () => api.get('/subjects/');
export const createSubject = (data) => api.post('/subjects/', data);
export const updateSubject = (id, data) => api.patch(`/subjects/${id}/`, data);
export const deleteSubject = (id) => api.delete(`/subjects/${id}/`);
export const getSkills = () => api.get('/skills/');
export const createSkill = (data) => api.post('/skills/', data);
export const updateSkill = (id, data) => api.patch(`/skills/${id}/`, data);
export const deleteSkill = (id) => api.delete(`/skills/${id}/`);
export const getSkillTree = (categoryId) => api.get(`/skills/tree/${categoryId}/`);
export const getSkillProgress = () => api.get('/skill-progress/');
export const getAchievementsSummary = () => api.get('/achievements/summary/');

// Rewards / Coins
export const getRewards = () => api.get('/rewards/');
export const createReward = (formData) => api.upload('/rewards/', formData);
export const updateReward = (id, formData) =>
  api.patch(`/rewards/${id}/`, formData);
export const deleteReward = (id) => api.delete(`/rewards/${id}/`);
export const redeemReward = (id) => api.post(`/rewards/${id}/redeem/`, {});
export const getRedemptions = () => api.get('/redemptions/');
export const approveRedemption = (id, notes = '') =>
  api.post(`/redemptions/${id}/approve/`, { notes });
export const rejectRedemption = (id, notes = '') =>
  api.post(`/redemptions/${id}/reject/`, { notes });
export const getCoinBalance = () => api.get('/coins/');
export const adjustCoins = (user_id, amount, description = '') =>
  api.post('/coins/adjust/', { user_id, amount, description });

// Coin Exchange
export const getExchangeRate = () => api.get('/coins/exchange/rate/');
export const requestExchange = (dollar_amount) =>
  api.post('/coins/exchange/', { dollar_amount });
export const getExchangeRequests = () => api.get('/coins/exchange/list/');
export const approveExchange = (id, notes = '') =>
  api.post(`/coins/exchange/${id}/approve/`, { notes });
export const rejectExchange = (id, notes = '') =>
  api.post(`/coins/exchange/${id}/reject/`, { notes });

// Portfolio
export const getPortfolio = () => api.get('/portfolio/');
export const getPhotos = () => api.get('/photos/');
export const uploadPhoto = (projectId, file, caption = '') => {
  const fd = new FormData();
  fd.append('project', projectId);
  fd.append('image', file);
  if (caption) fd.append('caption', caption);
  return api.upload('/photos/', fd);
};
export const deletePhoto = (id) => api.delete(`/photos/${id}/`);
export const deleteHomeworkProof = (id) => api.delete(`/homework-proofs/${id}/`);

// Avatar
export const uploadAvatar = (file) => {
  const fd = new FormData();
  fd.append('avatar', file);
  return api.patch('/auth/me/', fd);
};
export const removeAvatar = () => api.patch('/auth/me/', { avatar: '' });

// Categories
export const getCategories = () => api.get('/categories/');
export const createCategory = (data) => api.post('/categories/', data);
export const updateCategory = (id, data) => api.patch(`/categories/${id}/`, data);
export const deleteCategory = (id) => api.delete(`/categories/${id}/`);

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
export const updateTemplate = (id, data) => api.patch(`/templates/${id}/`, data);
export const deleteTemplate = (id) => api.delete(`/templates/${id}/`);
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

// QR Code
export const getProjectQR = (id) => getBlob(`/projects/${id}/qr/`);

// Collaborators
export const getCollaborators = (projectId) => api.get(`/projects/${projectId}/collaborators/`);
export const addCollaborator = (projectId, user_id, pay_split_percent) =>
  api.post(`/projects/${projectId}/collaborators/`, { user_id, pay_split_percent });

// Children (parent-only)
export const getChildren = () => api.get('/children/');
export const updateChild = (id, data) => api.patch(`/children/${id}/`, data);

// Chores
export const getChores = () => api.get('/chores/');
export const getChore = (id) => api.get(`/chores/${id}/`);
export const createChore = (data) => api.post('/chores/', data);
export const updateChore = (id, data) => api.patch(`/chores/${id}/`, data);
export const deleteChore = (id) => api.delete(`/chores/${id}/`);
export const completeChore = (id, notes = '') =>
  api.post(`/chores/${id}/complete/`, { notes });
export const getChoreCompletions = (status) => {
  const qs = status ? `?status=${status}` : '';
  return api.get(`/chore-completions/${qs}`);
};
export const approveChoreCompletion = (id) =>
  api.post(`/chore-completions/${id}/approve/`);
export const rejectChoreCompletion = (id) =>
  api.post(`/chore-completions/${id}/reject/`);

// Greenlight Import
export const importGreenlight = (user_id, csv_data) =>
  api.post('/greenlight/import/', { user_id, csv_data });

// Google OAuth
export const getGoogleAuthUrl = (forUserId) => {
  const qs = forUserId ? `?for_user=${forUserId}` : '';
  return api.get(`/auth/google/${qs}`);
};
export const getGoogleLoginUrl = () => api.get('/auth/google/login/');
export const getGoogleAccount = (forUserId) => {
  const qs = forUserId ? `?for_user=${forUserId}` : '';
  return api.get(`/auth/google/account/${qs}`);
};
export const unlinkGoogleAccount = (forUserId) => {
  const qs = forUserId ? `?for_user=${forUserId}` : '';
  return api.delete(`/auth/google/account/${qs}`);
};

// Google Calendar
export const getCalendarSettings = () => api.get('/auth/google/calendar/');
export const updateCalendarSettings = (data) => api.patch('/auth/google/calendar/', data);
export const triggerCalendarSync = () => api.post('/auth/google/calendar/sync/');

// Homework
export const getHomeworkDashboard = () => api.get('/homework/dashboard/');
export const getHomework = () => api.get('/homework/');
export const getHomeworkDetail = (id) => api.get(`/homework/${id}/`);
export const createHomework = (data) => api.post('/homework/', data);
export const updateHomework = (id, data) => api.patch(`/homework/${id}/`, data);
export const deleteHomework = (id) => api.delete(`/homework/${id}/`);
export const submitHomework = (id, formData) =>
  api.upload(`/homework/${id}/submit/`, formData);
export const saveHomeworkTemplate = (id) =>
  api.post(`/homework/${id}/save-template/`);
export const planHomework = (id) =>
  api.post(`/homework/${id}/plan/`);
export const getHomeworkSubmissions = (status) => {
  const qs = status ? `?status=${status}` : '';
  return api.get(`/homework-submissions/${qs}`);
};
export const approveHomeworkSubmission = (id) =>
  api.post(`/homework-submissions/${id}/approve/`);
export const rejectHomeworkSubmission = (id) =>
  api.post(`/homework-submissions/${id}/reject/`);
export const getHomeworkTemplates = () => api.get('/homework-templates/');
export const createHomeworkTemplate = (data) => api.post('/homework-templates/', data);
export const deleteHomeworkTemplate = (id) => api.delete(`/homework-templates/${id}/`);
export const createAssignmentFromTemplate = (templateId, data) =>
  api.post(`/homework-templates/${templateId}/create-assignment/`, data);

// RPG
export const getCharacterProfile = () => api.get('/character/');
export const getStreaks = () => api.get('/streaks/');
export const getHabits = () => api.get('/habits/');
export const createHabit = (data) => api.post('/habits/', data);
export const updateHabit = (id, data) => api.patch(`/habits/${id}/`, data);
export const deleteHabit = (id) => api.delete(`/habits/${id}/`);
export const logHabitTap = (id, direction) =>
  api.post(`/habits/${id}/log/`, { direction });
export const getInventory = () => api.get('/inventory/');
export const useConsumable = (itemId) =>
  api.post(`/inventory/${itemId}/use/`);
export const getRecentDrops = () => api.get('/drops/recent/');

// Pets
export const getStable = () => api.get('/pets/stable/');
export const hatchPet = (eggItemId, potionItemId) =>
  api.post('/pets/hatch/', { egg_item_id: eggItemId, potion_item_id: potionItemId });
export const feedPet = (petId, foodItemId) =>
  api.post(`/pets/${petId}/feed/`, { food_item_id: foodItemId });
export const activatePet = (petId) => api.post(`/pets/${petId}/activate/`);
export const getMounts = () => api.get('/mounts/');
export const activateMount = (mountId) => api.post(`/mounts/${mountId}/activate/`);

// Cosmetics
export const getCosmetics = () => api.get('/cosmetics/');
export const equipCosmetic = (itemId) => api.post('/character/equip/', { item_id: itemId });
export const unequipCosmetic = (slot) => api.post('/character/unequip/', { slot });

// Quests
export const getActiveQuest = () => api.get('/quests/active/');
export const getAvailableQuests = () => api.get('/quests/available/');
export const startQuest = (definitionId, scrollItemId) =>
  api.post('/quests/start/', { definition_id: definitionId, scroll_item_id: scrollItemId });
export const getQuestHistory = () => api.get('/quests/history/');
export const createQuest = (data) => api.post('/quests/', data);
export const assignQuest = (definitionId, userId) =>
  api.post(`/quests/${definitionId}/assign/`, { user_id: userId });
export const getFamilyQuests = () => api.get('/quests/family/');

// Sprites
/**
 * Fetches the runtime sprite catalog. No auth; endpoint is public.
 * Supports ETag revalidation via the optional `etag` argument — pass
 * the etag from a previous response and get 304 Not Modified back
 * (returned as { notModified: true }) if nothing changed.
 */
export async function fetchSpriteCatalog(etag = null) {
  const headers = { Accept: 'application/json' };
  if (etag) headers['If-None-Match'] = `"${etag}"`;
  const resp = await fetch('/api/sprites/catalog/', { headers });
  if (resp.status === 304) return { notModified: true };
  if (!resp.ok) throw new Error(`sprite catalog fetch failed: ${resp.status}`);
  return resp.json();
}

// Activity log (parent-only)
export const listActivity = (params = {}) => {
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');
  return api.get(`/activity/${qs ? `?${qs}` : ''}`);
};
// Cursor pagination returns absolute next/previous URLs — call them as-is
// minus the /api prefix the client auto-adds.
export const fetchActivityUrl = (url) => {
  if (!url) return Promise.resolve({ results: [], next: null, previous: null });
  const path = url.replace(/^https?:\/\/[^/]+/, '').replace(/^\/api/, '');
  return api.get(path);
};
