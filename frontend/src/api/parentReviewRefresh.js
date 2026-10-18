import { getToken } from './client';

export const PARENT_REVIEW_CHANGED = 'abby:parent-review-changed';

// Capture the credential before the write; a delayed response from a former
// account must never refresh the replacement family's workspace.
export async function withParentReviewRefresh(write) {
  const token = getToken();
  const result = await write;
  if (token === getToken()) window.dispatchEvent(new CustomEvent(PARENT_REVIEW_CHANGED, { detail: { token } }));
  return result;
}
