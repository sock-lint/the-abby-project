import { describe, expect, it } from 'vitest';
import { STORAGE_KEYS } from '../constants/storage';
import {
  activeProjectsOf,
  defaultClockProjectId,
  rememberClockProject,
  rememberedClockProject,
} from './clock';

const birdhouse = { id: 7, title: 'Birdhouse', status: 'active' };
const robot = { id: 8, title: 'Robot', status: 'in_progress' };
const finished = { id: 9, title: 'Old kite', status: 'completed' };

describe('activeProjectsOf', () => {
  it('keeps only active and in_progress projects', () => {
    expect(activeProjectsOf([birdhouse, robot, finished])).toEqual([birdhouse, robot]);
  });
});

describe('defaultClockProjectId', () => {
  it('returns the remembered venture when it is still active', () => {
    localStorage.setItem(STORAGE_KEYS.LAST_CLOCK_PROJECT, '8');
    expect(defaultClockProjectId([birdhouse, robot])).toBe('8');
  });

  it('falls back to the only active venture when nothing is remembered', () => {
    expect(defaultClockProjectId([birdhouse])).toBe('7');
  });

  it('returns "" when several ventures are active and nothing is remembered', () => {
    expect(defaultClockProjectId([birdhouse, robot])).toBe('');
  });

  it('ignores a remembered venture that is no longer in the active list', () => {
    localStorage.setItem(STORAGE_KEYS.LAST_CLOCK_PROJECT, '9');
    expect(defaultClockProjectId([birdhouse, robot])).toBe('');
    // …but still auto-selects a lone active venture.
    expect(defaultClockProjectId([birdhouse])).toBe('7');
  });
});

describe('rememberClockProject / rememberedClockProject', () => {
  it('round-trips the venture through localStorage', () => {
    rememberClockProject(7);
    expect(localStorage.getItem(STORAGE_KEYS.LAST_CLOCK_PROJECT)).toBe('7');
    expect(rememberedClockProject([birdhouse, robot])).toEqual(birdhouse);
  });

  it('returns null when nothing is remembered or the venture is gone', () => {
    expect(rememberedClockProject([birdhouse])).toBeNull();
    rememberClockProject(9);
    expect(rememberedClockProject([birdhouse, robot])).toBeNull();
  });
});
