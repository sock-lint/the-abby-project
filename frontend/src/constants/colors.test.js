import { describe, expect, it } from 'vitest';
import {
  RARITY_COLORS,
  RARITY_PILL_COLORS,
  RARITY_RING_COLORS,
  RARITY_TEXT_COLORS,
  STATUS_COLORS,
  STATUS_LABELS,
} from './colors.js';

describe('colors module', () => {
  it('STATUS_COLORS contains the expected statuses', () => {
    for (const k of [
      'draft', 'active', 'in_progress', 'in_review', 'completed', 'archived',
      'pending', 'approved', 'paid', 'disputed', 'voided',
      'fulfilled', 'denied', 'canceled', 'failed', 'expired',
    ]) {
      expect(STATUS_COLORS[k]).toBeTruthy();
    }
  });

  it('STATUS_LABELS only overrides keys that need humanizing', () => {
    expect(STATUS_LABELS.in_progress).toBe('In Progress');
    expect(STATUS_LABELS.in_review).toBe('In Review');
  });

  it.each(['common', 'uncommon', 'rare', 'epic', 'legendary'])(
    'rarity maps include %s',
    (key) => {
      expect(RARITY_COLORS[key]).toBeTruthy();
      expect(RARITY_PILL_COLORS[key]).toBeTruthy();
      expect(RARITY_TEXT_COLORS[key]).toBeTruthy();
      expect(RARITY_RING_COLORS[key]).toBeTruthy();
    },
  );
});
