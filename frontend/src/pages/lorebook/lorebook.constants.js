// Lorebook chapter taxonomy and economy helpers. Kept out of JSX so these
// shared constants can be reused by kid and parent renderers without tripping
// react-refresh/only-export-components.

import { chapterMark } from '../../components/atlas/mastery.constants';

export const LOREBOOK_CHAPTERS = [
  {
    id: 'daily_life',
    rubric: chapterMark(0),
    letter: 'D',
    name: 'Daily Life',
    kicker: 'Chores, habits, homework, movement, journals, and creations',
    entries: ['duties', 'rituals', 'study', 'movement', 'journal', 'creations'],
  },
  {
    id: 'long_work',
    rubric: chapterMark(1),
    letter: 'P',
    name: 'Projects & Skills',
    kicker: 'Projects, skills, badges, and memories',
    entries: ['ventures', 'skills', 'badges', 'chronicle'],
  },
  {
    id: 'rpg_layer',
    rubric: chapterMark(2),
    letter: 'C',
    name: 'Challenges & Pets',
    kicker: 'Challenges, pets, item drops, and streaks',
    entries: ['quests', 'pets', 'mounts', 'drops', 'streaks'],
  },
  {
    id: 'trade_coin',
    rubric: chapterMark(3),
    letter: 'M',
    name: 'Money & Coins',
    kicker: 'Coins, earnings, and payments',
    entries: ['coins', 'money'],
  },
  {
    id: 'self_expression',
    rubric: chapterMark(4),
    letter: 'P',
    name: 'Profile',
    kicker: 'Covers, titles, frames, and trophy badges',
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
  { key: 'quest_progress', label: 'Challenge', shortLabel: '⚔' },
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
    const trained = chapterEntries.filter((entry) => entry.trained).length;
    return {
      chapter,
      entries: chapterEntries,
      unlocked,
      trained,
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
