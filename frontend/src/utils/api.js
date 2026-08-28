// API response helpers.

/**
 * DRF paginates list endpoints as `{ count, results }` but some endpoints
 * return a raw array. `normalizeList` hides that difference so pages don't
 * repeat `data?.results || data || []` everywhere.
 */
export function normalizeList(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

/**
 * DRF answers a rejected write with `{field: ["message"], ...}`, sometimes
 * mixed with `detail` / `error` / `non_field_errors` for whole-object
 * problems. `fieldErrors` pulls out just the per-field half, flattened to
 * `{field: "message"}`, so a form can hang each message under the input that
 * caused it. Without it these bodies fall through to the client's
 * `JSON.stringify` fallback and the user reads raw JSON in a banner.
 */
export function fieldErrors(err) {
  const body = err?.response;
  if (!body || typeof body !== 'object' || Array.isArray(body)) return {};
  return Object.fromEntries(
    Object.entries(body)
      .filter(([key]) => !['detail', 'error', 'non_field_errors'].includes(key))
      .map(([key, value]) => [key, Array.isArray(value) ? value[0] : value])
      .filter(([, message]) => typeof message === 'string'),
  );
}
