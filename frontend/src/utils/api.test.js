import { describe, expect, it } from 'vitest';
import { fieldErrors, normalizeList } from './api.js';

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

describe('fieldErrors', () => {
  const err = (response) => Object.assign(new Error('x'), { response });

  it('flattens DRF per-field lists to one message each', () => {
    expect(fieldErrors(err({
      access_code: ['Enter the access code.', 'And again.'],
      host: ['Enter the IP.'],
    }))).toEqual({
      access_code: 'Enter the access code.',
      host: 'Enter the IP.',
    });
  });

  it('accepts a bare string as well as a list', () => {
    expect(fieldErrors(err({ serial: 'Already taken.' })))
      .toEqual({ serial: 'Already taken.' });
  });

  it('drops the whole-object keys a form has no input for', () => {
    expect(fieldErrors(err({
      detail: 'Nope.', error: 'Nope.', non_field_errors: ['Nope.'], host: ['Yes.'],
    }))).toEqual({ host: 'Yes.' });
  });

  it('drops values that are not messages', () => {
    expect(fieldErrors(err({ problems: [{ kind: 'over_budget' }], budget: 42 })))
      .toEqual({});
  });

  it('returns {} for an error carrying no parsed body', () => {
    expect(fieldErrors(new Error('network down'))).toEqual({});
    expect(fieldErrors(err(null))).toEqual({});
    expect(fieldErrors(err(['a', 'b']))).toEqual({});
    expect(fieldErrors(undefined)).toEqual({});
  });
});
