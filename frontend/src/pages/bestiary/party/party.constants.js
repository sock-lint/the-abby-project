// Mirrors apps/pets/services.py:MOUNT_BREEDING_COOLDOWN_DAYS. Stable
// game-design constant — safe to live client-side. Imported by both
// Mounts.jsx (filter pills) and Hatchery.jsx (breed-rest copy).
export const BREEDING_COOLDOWN_DAYS = 7;

const DAY_MS = 24 * 60 * 60 * 1000;

// Returns null when the mount is ready to breed again, otherwise the
// integer days remaining (rounded up so "less than a day" still reads as 1).
export function daysUntilReady(lastBredAt) {
  if (!lastBredAt) return null;
  const last = new Date(lastBredAt).getTime();
  if (Number.isNaN(last)) return null;
  const elapsedMs = Date.now() - last;
  const cooldownMs = BREEDING_COOLDOWN_DAYS * DAY_MS;
  if (elapsedMs >= cooldownMs) return null;
  return Math.max(1, Math.ceil((cooldownMs - elapsedMs) / DAY_MS));
}

// Higher number = rarer = sorts first in default order.
const RARITY_ORDER = {
  legendary: 5,
  epic: 4,
  rare: 3,
  uncommon: 2,
  common: 1,
};

export function compareByRarityThenName(a, b) {
  const ra = RARITY_ORDER[a.potion?.rarity] ?? 0;
  const rb = RARITY_ORDER[b.potion?.rarity] ?? 0;
  if (ra !== rb) return rb - ra;
  const na = a.species?.name || '';
  const nb = b.species?.name || '';
  return na.localeCompare(nb);
}

const HUNGRY_LEVELS = new Set(['bored', 'stale', 'away']);
const READY_TO_EVOLVE_THRESHOLD = 90;

// Soft, non-alarming copy under a companion's name when its happiness has
// drifted. Mirrors the buckets in ``apps/pets/services.py::happiness_for_pet``.
// ``happy`` and ``away`` are intentionally omitted: ``happy`` is the default
// (no whisper) and ``away`` (14+ days unfed) is conveyed visually by the
// strongest grayscale ramp on the sprite — adding text here would feel like
// a guilt-trip rather than a gentle nudge.
export const HAPPINESS_WHISPER = {
  bored: 'a little bored — feed me?',
  stale: 'getting hungry — needs a snack',
};

export const COMPANION_FILTERS = [
  { key: 'all',    label: 'All',             match: () => true },
  { key: 'active', label: 'Active',          match: (p) => !!p.is_active },
  { key: 'hungry', label: 'Hungry',          match: (p) => !p.evolved_to_mount && HUNGRY_LEVELS.has(p.happiness_level) },
  { key: 'ready',  label: 'Ready to evolve', match: (p) => !p.evolved_to_mount && (p.growth_points ?? 0) >= READY_TO_EVOLVE_THRESHOLD },
];

export const MOUNT_FILTERS = [
  { key: 'all',      label: 'All',             match: () => true },
  { key: 'active',   label: 'Active',          match: (m) => !!m.is_active },
  { key: 'on_expedition', label: 'Out exploring', match: (m) => !!m.active_expedition && m.active_expedition.status === 'active' },
  { key: 'ready',    label: 'Ready to breed',  match: (m) => daysUntilReady(m.last_bred_at) === null },
  { key: 'cooldown', label: 'On cooldown',     match: (m) => daysUntilReady(m.last_bred_at) !== null },
];

// Format remaining time for an out-on-expedition mount card. Returns
// "12m" / "1h 24m" / "ready" depending on seconds_remaining.
export function formatExpeditionRemaining(secondsRemaining) {
  if (secondsRemaining == null) return '';
  if (secondsRemaining <= 0) return 'ready';
  const totalMinutes = Math.ceil(secondsRemaining / 60);
  if (totalMinutes < 60) return `${totalMinutes}m`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
}
