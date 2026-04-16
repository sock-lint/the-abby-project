import { describe, expect, it } from 'vitest';
import { normalizeList } from './api.js';

describe('normalizeList', () => {
  it('returns an array unchanged', () => {
    const arr = [{ id: 1 }, { id: 2 }];
    expect(normalizeList(arr)).toBe(arr);
  });

  it('unwraps DRF-paginated shape', () => {
    const paginated = { count: 2, results: [{ id: 1 }, { id: 2 }] };
    expect(normalizeList(paginated)).toEqual(paginated.results);
  });

  it('returns [] for null', () => {
    expect(normalizeList(null)).toEqual([]);
  });

  it('returns [] for undefined', () => {
    expect(normalizeList(undefined)).toEqual([]);
  });

  it('returns [] for objects without a results key', () => {
    expect(normalizeList({ foo: 'bar' })).toEqual([]);
  });

  it('returns [] when results is not an array', () => {
    expect(normalizeList({ results: 'no' })).toEqual([]);
  });
});
