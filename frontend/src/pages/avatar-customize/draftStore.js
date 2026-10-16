import { AUTH_CHANGED_EVENT } from '../../api/client';
import { STORAGE_KEYS } from '../../constants/storage';

let activeScope = null;
const drafts = new Map();
const matches = (scope) => activeScope?.accountId === scope.accountId && activeScope?.credential === scope.credential;

export function resetAvatarDrafts() {
  activeScope = null;
  drafts.clear();
}

export function readAvatarDraft(scope, avatarId) {
  if (!scope.accountId || !scope.credential) { resetAvatarDrafts(); return undefined; }
  if (!matches(scope)) { resetAvatarDrafts(); activeScope = { ...scope }; }
  const draft = drafts.get(avatarId);
  return draft ? structuredClone(draft) : undefined;
}

export function writeAvatarDraft(scope, avatarId, preferences) {
  if (!matches(scope)) return;
  drafts.set(avatarId, structuredClone(preferences));
}

export function clearAvatarDraft(scope, avatarId) {
  if (matches(scope)) drafts.delete(avatarId);
}

// Retain only edits during same-session navigation. Never persist a catalog,
// character response, token or draft to browser storage; session changes drop
// every in-memory edit, including when the editor is currently unmounted.
window.addEventListener(AUTH_CHANGED_EVENT, resetAvatarDrafts);
window.addEventListener('storage', (event) => {
  if (event.key === null || event.key === STORAGE_KEYS.AUTH_TOKEN) resetAvatarDrafts();
});
