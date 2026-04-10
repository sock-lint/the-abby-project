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
