import {
  Stamp, Sparkles, Coins, Swords, Flame, Repeat, Clock, Settings2,
} from 'lucide-react';

// Category → icon + accent color for <EventRow>. Flat map keeps the row
// generic — no per-event-type switch statement. Add a key here when a new
// ActivityEvent.Category is introduced on the backend.
export const CATEGORY_META = {
  approval: {
    label: 'Approvals',
    icon: Stamp,
    accent: 'text-sheikah-teal-deep',
    bg: 'bg-sheikah-teal/10',
  },
  award: {
    label: 'Awards',
    icon: Sparkles,
    accent: 'text-gold-leaf',
    bg: 'bg-gold-leaf/10',
  },
  ledger: {
    label: 'Ledger',
    icon: Coins,
    accent: 'text-ember-deep',
    bg: 'bg-ember/10',
  },
  rpg: {
    label: 'RPG',
    icon: Flame,
    accent: 'text-ember-deep',
    bg: 'bg-ember/10',
  },
  quest: {
    label: 'Quests',
    icon: Swords,
    accent: 'text-royal',
    bg: 'bg-royal/10',
  },
  habit: {
    label: 'Habits',
    icon: Repeat,
    accent: 'text-moss',
    bg: 'bg-moss/10',
  },
  timecard: {
    label: 'Clock',
    icon: Clock,
    accent: 'text-sheikah-teal-deep',
    bg: 'bg-sheikah-teal/10',
  },
  system: {
    label: 'System',
    icon: Settings2,
    accent: 'text-ink-secondary',
    bg: 'bg-ink-page-shadow/30',
  },
};

export const CATEGORY_ORDER = [
  'approval', 'award', 'ledger', 'rpg', 'quest',
  'habit', 'timecard', 'system',
];

// Op glyph → how we render it between breakdown rows. "note" is just an
// info row with no preceding operator.
export const OP_GLYPH = {
  '+': '+',
  '-': '−',
  '×': '×',
  '÷': '÷',
  '=': '=',
  note: null,
};

export function categoryMeta(category) {
  return CATEGORY_META[category] || CATEGORY_META.system;
}

export function formatDayHeader(iso) {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  const sameDay = (a, b) =>
    a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();

  if (sameDay(d, today)) return 'Today';
  if (sameDay(d, yesterday)) return 'Yesterday';
  return d.toLocaleDateString(undefined, {
    weekday: 'long', month: 'short', day: 'numeric',
  });
}

export function dayKey(iso) {
  return iso.slice(0, 10); // YYYY-MM-DD
}
