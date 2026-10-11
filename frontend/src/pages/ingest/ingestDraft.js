const PREFIX = 'abby:ingest-draft:v1:';

export const DEFAULT_OVERRIDES = {
  category_id: '', difficulty: 2, bonus_amount: '0', materials_budget: '0', due_date: '',
};

export function ingestDraftKey(userId) {
  return Number.isInteger(userId) && userId > 0 ? `${PREFIX}${userId}` : null;
}

export function normalizeIngestDraft(draft = {}) {
  return {
    ...draft,
    milestones: Array.isArray(draft.milestones) ? draft.milestones : [],
    materials: Array.isArray(draft.materials) ? draft.materials : [],
    steps: Array.isArray(draft.steps) ? draft.steps : [],
    resources: Array.isArray(draft.resources) ? draft.resources : [],
  };
}

export function readIngestDraft(userId) {
  const key = ingestDraftKey(userId);
  if (!key) return null;
  try {
    const saved = JSON.parse(localStorage.getItem(key));
    if (saved?.version !== 1 || !['string', 'number'].includes(typeof saved.jobId)
      || !saved.jobId || typeof saved.url !== 'string'
      || !['url', 'pdf'].includes(saved.sourceTab)
      || typeof saved.pendingCommit !== 'boolean'
      || !saved.overrides || typeof saved.overrides !== 'object'
      || Array.isArray(saved.overrides)
      || (saved.draft !== null && (!saved.draft || typeof saved.draft !== 'object' || Array.isArray(saved.draft)))) return null;
    return {
      jobId: saved.jobId, url: saved.url, sourceTab: saved.sourceTab,
      draft: saved.draft ? normalizeIngestDraft(saved.draft) : null,
      overrides: { ...DEFAULT_OVERRIDES, ...saved.overrides },
      pendingCommit: saved.pendingCommit,
    };
  } catch {
    return null;
  }
}

export function storeIngestDraft(userId, snapshot) {
  const key = ingestDraftKey(userId);
  if (!key || !snapshot.jobId) return false;
  try {
    // Persist the staged plan and capture fields, never files or credentials.
    localStorage.setItem(key, JSON.stringify({ version: 1, ...snapshot }));
    return true;
  } catch {
    return false;
  }
}

export function clearIngestDraft(userId, jobId) {
  const key = ingestDraftKey(userId);
  if (!key) return;
  try {
    if (readIngestDraft(userId)?.jobId === jobId) localStorage.removeItem(key);
  } catch {
    // A confirmed server result remains available even if cleanup fails.
  }
}
