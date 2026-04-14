// Single source of truth for status + rarity color classes.
// Import from here instead of redefining per page.

export const STATUS_COLORS = {
  // Project statuses
  draft: 'bg-gray-500/20 text-gray-400',
  active: 'bg-blue-500/20 text-blue-400',
  in_progress: 'bg-amber-500/20 text-amber-400',
  in_review: 'bg-purple-500/20 text-purple-400',
  completed: 'bg-green-500/20 text-green-400',
  archived: 'bg-gray-500/20 text-gray-500',
  // Timecard + payment statuses
  pending: 'bg-yellow-500/20 text-yellow-400',
  approved: 'bg-green-500/20 text-green-400',
  paid: 'bg-emerald-500/20 text-emerald-400',
  disputed: 'bg-red-500/20 text-red-400',
  voided: 'bg-red-500/20 text-red-500',
  // Redemption statuses (richer palette used inside Rewards)
  fulfilled: 'bg-green-400/10 text-green-300 border-green-400/30',
  denied: 'bg-red-400/10 text-red-300 border-red-400/30',
  canceled: 'bg-gray-400/10 text-gray-300 border-gray-400/30',
  // Quest statuses
  failed: 'bg-red-500/20 text-red-400',
  expired: 'bg-gray-500/20 text-gray-400',
};

export const STATUS_LABELS = {
  in_progress: 'In Progress',
  in_review: 'In Review',
};

export const RARITY_COLORS = {
  common: 'border-rarity-common/30 bg-rarity-common/5',
  uncommon: 'border-rarity-uncommon/30 bg-rarity-uncommon/5',
  rare: 'border-rarity-rare/30 bg-rarity-rare/5',
  epic: 'border-rarity-epic/30 bg-rarity-epic/5',
  legendary: 'border-rarity-legendary/30 bg-rarity-legendary/5',
};

// Pill-shaped rarity badges (bg + text) — Inventory tiles, drop toasts.
export const RARITY_PILL_COLORS = {
  common: 'bg-gray-500/20 text-gray-300',
  uncommon: 'bg-green-500/20 text-green-400',
  rare: 'bg-blue-500/20 text-blue-400',
  epic: 'bg-purple-500/20 text-purple-400',
  legendary: 'bg-amber-500/20 text-amber-400',
};

// Text-only rarity swatches — small inline rarity labels (Stable).
export const RARITY_TEXT_COLORS = {
  common: 'text-gray-400',
  uncommon: 'text-green-400',
  rare: 'text-blue-400',
  epic: 'text-purple-400',
  legendary: 'text-amber-400',
};
