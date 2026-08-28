// Shared display formatters — import from here instead of inlining per page.

export function formatCurrency(amount) {
  const n = parseFloat(amount);
  if (Number.isNaN(n)) return '$0.00';
  return `$${n.toFixed(2)}`;
}

// The one duration format in the app: "45m" under an hour, "1h 5m" over it.
// Header pips, hero cards, timecards and clock entries all read the same, and
// a sub-hour value never renders as the clunky "0h 45m".
export function formatDuration(minutes) {
  const m = Number(minutes) || 0;
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (h === 0) return `${r}m`;
  return `${h}h ${r}m`;
}

// DRF DateField serializes as a bare "YYYY-MM-DD", which `new Date()` parses
// as UTC midnight — the previous evening in America/Phoenix, so every
// date-only value rendered a day early ("week of" Saturday on a Sunday
// timecard, yesterday's date on a duty completed today). Datetimes carry a
// zone and are left alone.
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

function toLocalDate(iso) {
  if (DATE_ONLY.test(iso)) {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date(iso);
}

export function formatDate(iso) {
  if (!iso) return '';
  return toLocalDate(iso).toLocaleDateString();
}

export function formatDateTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString();
}

export function formatMonth(iso) {
  if (!iso) return '';
  return toLocalDate(iso).toLocaleDateString(undefined, {
    year: 'numeric', month: 'long',
  });
}
