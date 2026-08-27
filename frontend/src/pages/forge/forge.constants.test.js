import { describe, expect, it } from 'vitest';
import {
  budgetProgress,
  formatCap,
  formatGrams,
  formatMinutes,
  isJobOpen,
  isOverage,
  jobProgressLabel,
  usagePercent,
} from './forge.constants';

describe('forge.constants', () => {
  it('formats grams and falls back to an em dash rather than "null g"', () => {
    expect(formatGrams(120)).toBe('120 g');
    expect(formatGrams('42.5')).toBe('42.5 g');
    expect(formatGrams(null)).toBe('—');
    expect(formatGrams(undefined)).toBe('—');
  });

  it('formats minutes with an hour part only above the hour', () => {
    expect(formatMinutes(45)).toBe('45m');
    expect(formatMinutes(200)).toBe('3h 20m');
    expect(formatMinutes(null)).toBe('—');
  });

  it('renders a null cap as "No cap" but keeps zero as a real cap', () => {
    expect(formatCap(null, 'grams')).toBe('No cap');
    expect(formatCap(undefined, 'minutes')).toBe('No cap');
    // Zero means "nothing this month" — a real value, not an absent one.
    expect(formatCap(0, 'grams')).toBe('0 g');
  });

  it('treats negative remaining as an overage', () => {
    expect(isOverage(-5)).toBe(true);
    expect(isOverage(0)).toBe(false);
    expect(isOverage(null)).toBe(false);
  });

  it('clamps usage percent and returns 0 when uncapped', () => {
    expect(usagePercent(50, 100)).toBe(50);
    expect(usagePercent(150, 100)).toBe(100);
    expect(usagePercent(50, null)).toBe(0);
  });

  it('only calls a job open while it is running or paused', () => {
    expect(isJobOpen({ state: 'running', finished_at: null })).toBe(true);
    expect(isJobOpen({ state: 'paused', finished_at: null })).toBe(true);
    expect(isJobOpen({ state: 'finished', finished_at: '2026-08-01T00:00:00Z' })).toBe(false);
    expect(isJobOpen(null)).toBe(false);
  });

  it('builds a progress label from the parts that exist', () => {
    expect(jobProgressLabel({
      percent_complete: 62, layer_num: 120, total_layer_num: 300, remaining_minutes: 45,
    })).toBe('62% · layer 120 of 300 · ~45m left');
    expect(jobProgressLabel({
      percent_complete: 3, layer_num: 0, total_layer_num: 0, remaining_minutes: null,
    })).toBe('3%');
  });

  it('summarises budget progress across children, and says so when nobody has a cap', () => {
    expect(budgetProgress([
      { grams_per_month: '500.00', grams_used: '250.00' },
      { grams_per_month: '500.00', grams_used: '0.00' },
    ])).toEqual({ pct: 25, label: '250 g of 1000 g this month' });

    expect(budgetProgress([{ grams_per_month: null, grams_used: '0.00' }]))
      .toEqual({ pct: 0, label: 'no filament cap set' });
  });
});
