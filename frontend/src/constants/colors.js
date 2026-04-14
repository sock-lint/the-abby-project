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
};

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
