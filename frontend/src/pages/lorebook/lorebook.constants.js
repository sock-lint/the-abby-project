// Lorebook chapter taxonomy and economy helpers. Kept out of JSX so these
// shared constants can be reused by kid and parent renderers without tripping
// react-refresh/only-export-components.

export const LOREBOOK_CHAPTERS = [
  {
    id: 'daily_life',
    rubric: '§I',
    letter: 'D',
    name: 'Daily Life',
    kicker: 'duties, rituals, study, journal, creations',
    entries: ['duties', 'rituals', 'study', 'journal', 'creations'],
  },
  {
    id: 'long_work',
    rubric: '§II',
    letter: 'L',
    name: 'Long Work',
    kicker: 'ventures, skill trees, seals, chapters',
    entries: ['ventures', 'skills', 'badges', 'chronicle'],
  },
  {
    id: 'rpg_layer',
    rubric: '§III',
    letter: 'R',
    name: 'RPG Layer',
    kicker: 'quests, companions, treasure, flame',
    entries: ['quests', 'pets', 'mounts', 'drops', 'streaks'],
  },
  {
    id: 'trade_coin',
    rubric: '§IV',
    letter: 'T',
    name: 'Trade & Coin',
    kicker: 'game coins and real ledgers',
    entries: ['coins', 'money'],
  },
  {
    id: 'self_expression',
    rubric: '§V',
    letter: 'S',
    name: 'Self-Expression',
    kicker: 'covers, titles, frames, trophies',
    entries: ['cosmetics'],
  },
];

export const LOREBOOK_CHAPTERS_BY_ID = Object.fromEntries(
  LOREBOOK_CHAPTERS.map((chapter) => [chapter.id, chapter]),
);

export const ECONOMY_FLAGS = [
  { key: 'money', label: 'Money', shortLabel: '$' },
  { key: 'coins', label: 'Coins', shortLabel: 'c' },
  { key: 'xp', label: 'XP', shortLabel: 'XP' },
  { key: 'drops', label: 'Drops', shortLabel: '🎁' },
  { key: 'quest_progress', label: 'Quest', shortLabel: '⚔' },
  { key: 'streak_credit', label: 'Streak', shortLabel: '🔥' },
];

const ENTRY_ORDER = new Map(
  LOREBOOK_CHAPTERS.flatMap((chapter, chapterIndex) =>
    chapter.entries.map((slug, entryIndex) => [
      slug,
      { chapterIndex, entryIndex },
    ])),
);

export function sortEntries(entries = []) {
  return [...entries].sort((a, b) => {
    const ao = ENTRY_ORDER.get(a?.slug) ?? { chapterIndex: 99, entryIndex: 99 };
    const bo = ENTRY_ORDER.get(b?.slug) ?? { chapterIndex: 99, entryIndex: 99 };
    return (
      ao.chapterIndex - bo.chapterIndex
      || ao.entryIndex - bo.entryIndex
      || (a?.title || '').localeCompare(b?.title || '')
    );
  });
}

export function groupEntriesByChapter(entries = []) {
  const buckets = new Map(LOREBOOK_CHAPTERS.map((chapter) => [chapter.id, []]));
  for (const entry of sortEntries(entries)) {
    const chapterId = entry?.chapter || 'daily_life';
    const bucket = buckets.get(chapterId) ?? buckets.get('daily_life');
    bucket.push(entry);
  }

  return LOREBOOK_CHAPTERS.map((chapter) => {
    const chapterEntries = buckets.get(chapter.id) ?? [];
    const unlocked = chapterEntries.filter((entry) => entry.unlocked).length;
    return {
      chapter,
      entries: chapterEntries,
      unlocked,
      total: chapterEntries.length,
    };
  });
}

export function economyFlagLabel(flag) {
  return ECONOMY_FLAGS.find((item) => item.key === flag)?.label || flag;
}

export function economyFlagValue(entry, key) {
  return Boolean(entry?.economy?.[key]);
}
