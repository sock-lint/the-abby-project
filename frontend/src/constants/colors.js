// Single source of truth for status + rarity color classes.
// Reskinned for the Hyrule Field Notes journal aesthetic — sepia ink
// on parchment with Sheikah-teal and rarity-tier accents. Export names
// stay identical so call sites don't need to migrate all at once.

export const STATUS_COLORS = {
  // Project statuses
  draft: 'bg-ink-whisper/15 text-ink-secondary border border-ink-whisper/30',
  active: 'bg-sheikah-teal-deep/15 text-sheikah-teal-deep border border-sheikah-teal-deep/30',
  in_progress: 'bg-ember/15 text-ember-deep border border-ember/30',
  in_review: 'bg-royal/15 text-royal border border-royal/30',
  completed: 'bg-moss/20 text-moss border border-moss/40',
  archived: 'bg-ink-whisper/10 text-ink-whisper border border-ink-whisper/25',
  // Timecard + payment statuses
  pending: 'bg-gold-leaf/15 text-ember-deep border border-gold-leaf/40',
  approved: 'bg-moss/20 text-moss border border-moss/40',
  paid: 'bg-moss/25 text-moss border border-moss/50',
  disputed: 'bg-ember/20 text-ember-deep border border-ember/40',
  voided: 'bg-ember-deep/20 text-ember-deep border border-ember-deep/40',
  // Redemption statuses
  fulfilled: 'bg-moss/15 text-moss border border-moss/40',
  denied: 'bg-ember-deep/15 text-ember-deep border border-ember-deep/40',
  canceled: 'bg-ink-whisper/15 text-ink-secondary border border-ink-whisper/30',
  // Quest statuses
  failed: 'bg-ember-deep/15 text-ember-deep border border-ember-deep/40',
  expired: 'bg-ink-whisper/15 text-ink-secondary border border-ink-whisper/30',
  // Forge (3D print request) statuses. `pending` / `approved` / `completed` /
  // `failed` above already cover four of the seven; these are the three the
  // print lifecycle adds. Note `cancelled` (two Ls) is the Django spelling on
  // PrintRequest.Status — distinct from the older `canceled` redemption row.
  rejected: 'bg-ember-deep/15 text-ember-deep border border-ember-deep/40',
  printing: 'bg-sheikah-teal/20 text-sheikah-teal-deep border border-sheikah-teal/50',
  cancelled: 'bg-ink-whisper/15 text-ink-secondary border border-ink-whisper/30',
};

// Only statuses whose display label isn't just the capitalized key belong
// here — StatusBadge falls back to capitalizing the status itself, which is
// already right for the Forge lifecycle (Pending / Approved / Printing /
// Completed / Failed / Rejected / Cancelled).
export const STATUS_LABELS = {
  in_progress: 'In Progress',
  in_review: 'In Review',
};

// Rarity tier surfaces — tinted parchment panel + matching border.
export const RARITY_COLORS = {
  common: 'border-moss/40 bg-moss/10',
  uncommon: 'border-sheikah-teal/40 bg-sheikah-teal/10',
  rare: 'border-royal/40 bg-royal/10',
  epic: 'border-ember/40 bg-ember/10',
  legendary: 'border-gold-leaf/50 bg-gold-leaf/15',
};

// Pill-shaped rarity badges — Inventory tiles, drop toasts.
export const RARITY_PILL_COLORS = {
  common: 'bg-moss/20 text-moss',
  uncommon: 'bg-sheikah-teal/20 text-sheikah-teal-deep',
  rare: 'bg-royal/20 text-royal',
  epic: 'bg-ember/20 text-ember-deep',
  legendary: 'bg-gold-leaf/25 text-ember-deep',
};

// Text-only rarity swatches — inline labels.
export const RARITY_TEXT_COLORS = {
  common: 'text-moss',
  uncommon: 'text-sheikah-teal-deep',
  rare: 'text-royal',
  epic: 'text-ember-deep',
  legendary: 'text-gold-leaf',
};

// Rarity ring — used to frame bestiary/drop/pet cards.
export const RARITY_RING_COLORS = {
  common: 'ring-moss/50',
  uncommon: 'ring-sheikah-teal/60',
  rare: 'ring-royal/60',
  epic: 'ring-ember/60',
  legendary: 'ring-gold-leaf/70',
};

// Rarity outline — a solid tier border with no surface fill, for cards that
// already own their background (the RareDropReveal parchment card).
export const RARITY_BORDER_COLORS = {
  common: 'border-moss',
  uncommon: 'border-sheikah-teal',
  rare: 'border-royal',
  epic: 'border-ember',
  legendary: 'border-gold-leaf',
};

// Filled rarity chips — a solid tier surface carrying white text (the drop
// and savings toasts). These read the cover-invariant --color-rarity-*
// tokens rather than the per-cover `tones`: the dark Vigil cover inverts
// gold-leaf / royal / ember to light values, which would strand white text
// on a pale chip. Same hues as the maps above on every other cover.
export const RARITY_SOLID_COLORS = {
  common: 'bg-rarity-common',
  uncommon: 'bg-rarity-uncommon',
  rare: 'bg-rarity-rare',
  epic: 'bg-rarity-epic',
  legendary: 'bg-rarity-legendary',
};

// Raw tier colors for the few places that need a value rather than a utility
// class (the RareDropReveal box-shadow glow). These follow the cover's tones
// so the glow stays visible on the dark Vigil page.
export const RARITY_GLOW_COLORS = {
  common: 'var(--color-moss)',
  uncommon: 'var(--color-sheikah-teal)',
  rare: 'var(--color-royal)',
  epic: 'var(--color-ember)',
  legendary: 'var(--color-gold-leaf)',
};
