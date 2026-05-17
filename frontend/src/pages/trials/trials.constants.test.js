import { describe, expect, it } from 'vitest';
import {
  CHAPTERS,
  KIND_FILTERS,
  chapterIdForQuest,
  groupQuestsByChapter,
  kindCounts,
  overallProgress,
} from './trials.constants.js';

const defBoss = (overrides = {}) => ({
  id: 1, name: 'Dragon Slayer', quest_type: 'boss', required_badge: null, ...overrides,
});
const defCollection = (overrides = {}) => ({
  id: 2, name: 'Berry Hunt', quest_type: 'collection', required_badge: null, ...overrides,
});
const questOf = (definition, status = 'active', participants = []) => ({
  id: 99, status, definition, participants,
});

describe('CHAPTERS', () => {
  it('exposes the four status chapters in the expected order', () => {
    expect(CHAPTERS.map((c) => c.id)).toEqual([
      'available', 'underway', 'closed', 'locked',
    ]);
    expect(CHAPTERS.map((c) => c.rubric)).toEqual(['§I', '§II', '§III', '§IV']);
  });
});

describe('chapterIdForQuest', () => {
  it('classifies a plain QuestDefinition as available', () => {
    expect(chapterIdForQuest(defBoss(), { earnedBadgeIds: new Set() }))
      .toBe('available');
  });

  it('classifies a badge-gated definition without the badge as locked', () => {
    const def = defBoss({ required_badge: 42 });
    expect(chapterIdForQuest(def, { earnedBadgeIds: new Set() }))
      .toBe('locked');
  });

  it('classifies a badge-gated definition WITH the badge as available', () => {
    const def = defBoss({ required_badge: 42 });
    expect(chapterIdForQuest(def, { earnedBadgeIds: new Set([42]) }))
      .toBe('available');
  });

  it('also reads the snake-case required_badge_id alias', () => {
    const def = { id: 5, quest_type: 'boss', required_badge_id: 7 };
    expect(chapterIdForQuest(def, { earnedBadgeIds: new Set() }))
      .toBe('locked');
  });

  it('treats an active Quest row as underway', () => {
    const q = questOf(defBoss(), 'active');
    expect(chapterIdForQuest(q, { isQuest: true })).toBe('underway');
  });

  it('treats a non-active Quest row (completed/expired/failed) as closed', () => {
    expect(chapterIdForQuest(questOf(defBoss(), 'completed'), { isQuest: true }))
      .toBe('closed');
    expect(chapterIdForQuest(questOf(defBoss(), 'expired'), { isQuest: true }))
      .toBe('closed');
    expect(chapterIdForQuest(questOf(defBoss(), 'failed'), { isQuest: true }))
      .toBe('closed');
  });
});

describe('groupQuestsByChapter', () => {
  it('returns every chapter even when buckets are empty', () => {
    const grouped = groupQuestsByChapter({});
    expect(grouped).toHaveLength(4);
    grouped.forEach((g) => {
      expect(g.count).toBe(0);
      expect(g.quests).toEqual([]);
    });
  });

  it('fans definitions into available + locked using the earned badge set', () => {
    const grouped = groupQuestsByChapter({
      available: [
        defBoss({ id: 1 }),
        defCollection({ id: 2, required_badge: 99 }),
        defBoss({ id: 3, required_badge: 7 }),
      ],
      earnedBadgeIds: new Set([7]),
    });
    const byId = Object.fromEntries(grouped.map((g) => [g.chapter.id, g]));
    expect(byId.available.quests.map((q) => q.id).sort()).toEqual([1, 3]);
    expect(byId.locked.quests.map((q) => q.id)).toEqual([2]);
  });

  it('places the active quest in underway and history in closed', () => {
    const active = questOf(defBoss(), 'active');
    const completed = { id: 50, status: 'completed', definition: defBoss({ id: 1 }), participants: [] };
    const expired = { id: 51, status: 'expired', definition: defCollection({ id: 2 }), participants: [] };
    const grouped = groupQuestsByChapter({
      activeQuest: active,
      history: [completed, expired],
    });
    const byId = Object.fromEntries(grouped.map((g) => [g.chapter.id, g]));
    expect(byId.underway.quests).toEqual([active]);
    expect(byId.closed.quests.map((q) => q.id).sort()).toEqual([50, 51]);
  });
});

describe('KIND_FILTERS', () => {
  it('exposes the four kind filters', () => {
    expect(KIND_FILTERS.map((f) => f.key)).toEqual(['all', 'boss', 'collection', 'coop']);
  });

  it('matches by quest_type on a QuestDefinition', () => {
    const boss = KIND_FILTERS.find((f) => f.key === 'boss');
    expect(boss.match(defBoss())).toBe(true);
    expect(boss.match(defCollection())).toBe(false);
  });

  it('matches by nested definition.quest_type on a Quest row', () => {
    const boss = KIND_FILTERS.find((f) => f.key === 'boss');
    expect(boss.match(questOf(defBoss(), 'completed'))).toBe(true);
  });

  it('coop matches Quest rows with >1 participant', () => {
    const coop = KIND_FILTERS.find((f) => f.key === 'coop');
    expect(coop.match(questOf(defBoss(), 'active', [{ id: 1 }, { id: 2 }]))).toBe(true);
    expect(coop.match(questOf(defBoss(), 'active', [{ id: 1 }]))).toBe(false);
    expect(coop.match(defBoss())).toBe(false); // QuestDefinitions are never co-op
  });
});

describe('kindCounts', () => {
  it('counts each kind across a mixed list', () => {
    const counts = kindCounts([
      defBoss({ id: 1 }),
      defBoss({ id: 2 }),
      defCollection({ id: 3 }),
      questOf(defBoss({ id: 4 }), 'completed', [{ id: 1 }, { id: 2 }]),
    ]);
    expect(counts.all).toBe(4);
    expect(counts.boss).toBe(3);
    expect(counts.collection).toBe(1);
    expect(counts.coop).toBe(1);
  });
});

describe('overallProgress', () => {
  it('returns 0/0 when nothing is available or completed', () => {
    expect(overallProgress({})).toEqual({ triumphs: 0, total: 0, progressPct: 0 });
  });

  it('counts completed history toward triumphs and ignores expired/failed', () => {
    const completed = { id: 1, status: 'completed' };
    const expired = { id: 2, status: 'expired' };
    const failed = { id: 3, status: 'failed' };
    const r = overallProgress({
      history: [completed, expired, failed],
      available: [defBoss({ id: 10 })],
    });
    // Denominator = triumphs (1) + active (0) + available (1) = 2.
    // Expired/failed don't pad it — they're closed-not-completed.
    expect(r).toEqual({ triumphs: 1, total: 2, progressPct: 50 });
  });

  it('includes the active quest in the denominator', () => {
    const r = overallProgress({
      history: [{ id: 1, status: 'completed' }, { id: 2, status: 'completed' }],
      activeQuest: { id: 99, status: 'active' },
      available: [],
    });
    // 2 triumphs + 1 active = 3 total; 2/3 ≈ 67%.
    expect(r).toEqual({ triumphs: 2, total: 3, progressPct: 67 });
  });
});
