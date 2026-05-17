// Pure-data exports for the Trials codex's chapter taxonomy + kind filter.
// Mirrors the shape of pages/bestiary/codex/codex.constants.js so the two
// codexes speak the same vocabulary. Lives in a .js file (not .jsx) so the
// react-refresh/only-export-components lint rule stays satisfied.

import { PROGRESS_TIER } from '../../components/atlas/mastery.constants';

// Status → tone for RuneBadge chips on tiles. Lifted from the old
// pages/Trials.jsx:27-32 so the closed-chapter tiles keep the same
// completed/expired/failed colors they had pre-redesign.
export const STATUS_TONE = {
  active: 'teal',
  completed: 'moss',
  expired: 'ink',
  failed: 'ember',
};

// Chapter definitions. `rubric` is the §-numeral the folio header renders;
// `letter` is the IlluminatedVersal drop-cap. `tier` is the spine-tint hint
// — `groupQuestsByChapter` still computes a progress-based tier per chapter
// at call time so empty chapters fall back to `locked` correctly.
export const CHAPTERS = [
  {
    id: 'available',
    name: 'Available',
    letter: 'A',
    rubric: '§I',
    kicker: 'boards posting fresh trials',
    tier: PROGRESS_TIER.rising,
  },
  {
    id: 'underway',
    name: 'Underway',
    letter: 'U',
    rubric: '§II',
    kicker: 'pressing forward — one at a time',
    tier: PROGRESS_TIER.cresting,
  },
  {
    id: 'closed',
    name: 'Closed',
    letter: 'C',
    rubric: '§III',
    kicker: 'trials filed in the chronicle',
    tier: PROGRESS_TIER.gilded,
  },
  {
    id: 'locked',
    name: 'Locked',
    letter: 'L',
    rubric: '§IV',
    kicker: 'badge-gated — earn the seal to unlock',
    tier: PROGRESS_TIER.locked,
  },
];

// Kind filter vessels — orthogonal to status chapters. Matches the
// Companions/Mounts shelf pattern: icon + label + match predicate, rendered
// as a TomeShelf with variant="vessel" and ×N chips.
export const KIND_FILTERS = [
  { key: 'all',        label: 'All',        icon: '🗺', match: () => true },
  { key: 'boss',       label: 'Boss',       icon: '🐲', match: (q) => kindOf(q) === 'boss' },
  { key: 'collection', label: 'Collection', icon: '📜', match: (q) => kindOf(q) === 'collection' },
  { key: 'coop',       label: 'Co-op',      icon: '🤝', match: (q) => isCoOp(q) },
];

// Pull the quest_type off either a QuestDefinition row (Available/Locked)
// or a Quest row carrying a nested .definition (Underway/Closed).
function kindOf(quest) {
  return quest?.definition?.quest_type ?? quest?.quest_type ?? null;
}

// Co-op is decided at start time, not on the QuestDefinition. For history
// + underway rows we can read participants.length; available-chapter
// QuestDefinitions can never satisfy this filter (the participant table
// doesn't exist yet), which is the correct behavior — picking Co-op
// while browsing available shows an empty grid.
function isCoOp(quest) {
  const parts = quest?.participants;
  return Array.isArray(parts) && parts.length > 1;
}

// Classify a single record into a chapter id. Available/Locked entries
// are QuestDefinition rows; Underway/Closed entries are Quest rows.
// `activeQuestId` is the in-progress Quest's id (used to distinguish
// the lone underway row from a separate available row sharing the
// definition).
export function chapterIdForQuest(record, { activeQuestId, earnedBadgeIds, isQuest } = {}) {
  if (!record) return 'available';
  if (isQuest) {
    if (record.status === 'active' || record.id === activeQuestId) return 'underway';
    return 'closed';
  }
  // QuestDefinition path. Locked = requires a badge the user hasn't earned.
  const required = record.required_badge ?? record.required_badge_id ?? null;
  if (required != null && !earnedBadgeIds?.has(required)) return 'locked';
  return 'available';
}

// Group quest sources into their four chapters. Returns the full ordered
// chapter list (including empty chapters) so the shelf renders a complete
// skeleton — empty chapters still draw a spine, matching BestiaryCodex.
export function groupQuestsByChapter({
  available = [],
  activeQuest = null,
  history = [],
  earnedBadgeIds = new Set(),
}) {
  const buckets = new Map(CHAPTERS.map((c) => [c.id, []]));

  for (const def of available) {
    const id = chapterIdForQuest(def, { earnedBadgeIds, isQuest: false });
    buckets.get(id)?.push(def);
  }
  if (activeQuest) {
    buckets.get('underway')?.push(activeQuest);
  }
  for (const q of history) {
    buckets.get('closed')?.push(q);
  }

  return CHAPTERS.map((chapter) => {
    const list = buckets.get(chapter.id) || [];
    return {
      chapter,
      quests: list,
      count: list.length,
    };
  });
}

// Counts per kind filter across a flat quest list — used to render the
// `×N` chip on each vessel pill. Empty buckets stay in the map so callers
// can render `×0` if they want (we hide them at render time).
export function kindCounts(quests = []) {
  const out = {};
  for (const filter of KIND_FILTERS) {
    out[filter.key] = quests.filter(filter.match).length;
  }
  return out;
}

// Overall progress for the IncipitBand hero: how many of the user's
// in-system quests have been triumphantly completed. Available-only
// quests count toward the denominator; locked don't (they're invisible
// until earned).
export function overallProgress({ history = [], available = [], activeQuest = null }) {
  const triumphs = history.filter((q) => q.status === 'completed').length;
  const total = triumphs + (activeQuest ? 1 : 0) + available.length;
  if (!total) return { triumphs, total: 0, progressPct: 0 };
  return {
    triumphs,
    total,
    progressPct: Math.round((triumphs / total) * 100),
  };
}
