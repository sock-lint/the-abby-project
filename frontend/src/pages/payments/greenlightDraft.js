// Keep a submitted transfer's identity across a lost response, sheet close or
// page refresh. Drafts belong to one parent/family/child, never to the page URL.
const PREFIX = 'abby_greenlight_pending_transfer:';

export function readPendingTransfer(ownerKey, userId) {
  if (!ownerKey) return null;
  try {
    const saved = JSON.parse(sessionStorage.getItem(`${PREFIX}${ownerKey}`));
    if (saved?.payload?.user_id !== Number(userId) || typeof saved.payload.idempotency_key !== 'string') return null;
    return saved;
  } catch {
    return null;
  }
}

export function savePendingTransfer(ownerKey, pending) {
  if (!ownerKey) return;
  try {
    if (pending) sessionStorage.setItem(`${PREFIX}${ownerKey}`, JSON.stringify(pending));
    else sessionStorage.removeItem(`${PREFIX}${ownerKey}`);
  } catch {
    // An in-memory retry remains available when device storage is unavailable.
  }
}
