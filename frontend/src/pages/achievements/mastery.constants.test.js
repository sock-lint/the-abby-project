import { describe, it, expect } from 'vitest';
import {
  PROGRESS_TIER,
  tierForProgress,
  RARITY_HALO,
  CHAPTER_NUMERALS,
  chapterMark,
  countIlluminated,
  isRecentlyEarned,
  RECENT_EARNED_DAYS,
} from './mastery.constants';

describe('PROGRESS_TIER', () => {
  it('has five keyed entries with bar + chip class strings', () => {
    for (const key of ['locked', 'nascent', 'rising', 'cresting', 'gilded']) {
      expect(PROGRESS_TIER[key]).toMatchObject({
        bar: expect.any(String),
        chip: expect.any(String),
      });
    }
  });
});

describe('tierForProgress', () => {
  it('returns locked tier when skill is locked', () => {
    expect(tierForProgress({ unlocked: false, progressPct: 0, level: 0 })).toBe(PROGRESS_TIER.locked);
    expect(tierForProgress({ unlocked: false, progressPct: 80, level: 3 })).toBe(PROGRESS_TIER.locked);
  });

  it('returns gilded tier when level is at or above maxLevel', () => {
    expect(tierForProgress({ unlocked: true, progressPct: 0, level: 6, maxLevel: 6 })).toBe(PROGRESS_TIER.gilded);
    expect(tierForProgress({ unlocked: true, progressPct: 0, level: 7, maxLevel: 6 })).toBe(PROGRESS_TIER.gilded);
  });

  it('returns gilded tier when progressPct >= 90 and unlocked', () => {
    expect(tierForProgress({ unlocked: true, progressPct: 90, level: 2 })).toBe(PROGRESS_TIER.gilded);
    expect(tierForProgress({ unlocked: true, progressPct: 100, level: 2 })).toBe(PROGRESS_TIER.gilded);
  });

  it('returns cresting tier for 60-89% progress', () => {
    expect(tierForProgress({ unlocked: true, progressPct: 60, level: 2 })).toBe(PROGRESS_TIER.cresting);
    expect(tierForProgress({ unlocked: true, progressPct: 89.9, level: 2 })).toBe(PROGRESS_TIER.cresting);
  });

  it('returns rising tier for 25-59% progress', () => {
    expect(tierForProgress({ unlocked: true, progressPct: 25, level: 1 })).toBe(PROGRESS_TIER.rising);
    expect(tierForProgress({ unlocked: true, progressPct: 59.9, level: 1 })).toBe(PROGRESS_TIER.rising);
  });

  it('returns nascent tier for 0-24% progress', () => {
    expect(tierForProgress({ unlocked: true, progressPct: 0, level: 1 })).toBe(PROGRESS_TIER.nascent);
    expect(tierForProgress({ unlocked: true, progressPct: 24.9, level: 1 })).toBe(PROGRESS_TIER.nascent);
  });
});

describe('RARITY_HALO', () => {
  it('has entries for every rarity tier', () => {
    for (const key of ['common', 'uncommon', 'rare', 'epic', 'legendary']) {
      expect(typeof RARITY_HALO[key]).toBe('string');
      expect(RARITY_HALO[key].length).toBeGreaterThan(0);
    }
  });
});

describe('CHAPTER_NUMERALS + chapterMark', () => {
  it('exposes 12 roman chapter markers', () => {
    expect(CHAPTER_NUMERALS).toHaveLength(12);
    expect(CHAPTER_NUMERALS[0]).toBe('§I');
    expect(CHAPTER_NUMERALS[11]).toBe('§XII');
  });

  it('returns the roman numeral for in-range indices', () => {
    expect(chapterMark(0)).toBe('§I');
    expect(chapterMark(2)).toBe('§III');
    expect(chapterMark(11)).toBe('§XII');
  });

  it('falls back to arabic for out-of-range indices', () => {
    expect(chapterMark(12)).toBe('§13');
    expect(chapterMark(20)).toBe('§21');
  });
});

describe('countIlluminated', () => {
  it('returns 0/0 for empty subjects list', () => {
    expect(countIlluminated([])).toEqual({ illuminated: 0, total: 0 });
  });

  it('counts unlocked skills with xp > 0 as illuminated', () => {
    const subjects = [
      {
        skills: [
          { unlocked: true, xp_points: 150 },
          { unlocked: true, xp_points: 0 },
          { unlocked: false, xp_points: 0 },
        ],
      },
      {
        skills: [
          { unlocked: true, xp_points: 10 },
          { unlocked: false, xp_points: 0 },
        ],
      },
    ];
    expect(countIlluminated(subjects)).toEqual({ illuminated: 2, total: 5 });
  });

  it('ignores subjects with no skills array', () => {
    expect(countIlluminated([{ skills: null }, { skills: [{ unlocked: true, xp_points: 5 }] }])).toEqual({
      illuminated: 1,
      total: 1,
    });
  });
});

describe('isRecentlyEarned', () => {
  it('returns false for null/undefined earned_at', () => {
    expect(isRecentlyEarned(null)).toBe(false);
    expect(isRecentlyEarned(undefined)).toBe(false);
  });

  it('returns true for an earned_at within RECENT_EARNED_DAYS', () => {
    const recent = new Date(Date.now() - 1000 * 60 * 60 * 24 * (RECENT_EARNED_DAYS - 1)).toISOString();
    expect(isRecentlyEarned(recent)).toBe(true);
  });

  it('returns false for an earned_at older than RECENT_EARNED_DAYS', () => {
    const old = new Date(Date.now() - 1000 * 60 * 60 * 24 * (RECENT_EARNED_DAYS + 1)).toISOString();
    expect(isRecentlyEarned(old)).toBe(false);
  });

  it('returns false for an unparseable earned_at', () => {
    expect(isRecentlyEarned('not a date')).toBe(false);
  });
});

describe('RECENT_EARNED_DAYS', () => {
  it('is a positive integer', () => {
    expect(Number.isInteger(RECENT_EARNED_DAYS)).toBe(true);
    expect(RECENT_EARNED_DAYS).toBeGreaterThan(0);
  });
});
