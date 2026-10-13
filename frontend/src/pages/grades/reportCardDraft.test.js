import { describe, expect, it, vi } from 'vitest';
import { gradeDraftKey, newGradeRequestId, storeGradeDraft } from './gradeDraft';
import {
  clearReportCardDraft, reportCardDraftKey, reportCardPayload, readReportCardDraft,
  storeReportCardDraft, validateReportCardFields,
} from './reportCardDraft';

function draft(overrides = {}) {
  return {
    mode: 'create', entry_id: null, client_entry_id: newGradeRequestId(),
    period_type: 'quarter', period_number: '1', school_year: '2025',
    subjects: [{ subject: 'Math', grade_format: 'percentage', score: '0', possible: '', letter: '' }],
    reflection: '', occurred_on: '2026-01-01', is_private: true, pending: null,
    ...overrides,
  };
}

describe('report card fields', () => {
  it('keeps mixed recorded grade formats in a single period without inactive values', () => {
    const fields = draft({
      period_type: 'semester', period_number: '2', subjects: [
        { subject: ' Math ', grade_format: 'percentage', score: '0', possible: '100', letter: 'A' },
        { subject: 'Art', grade_format: 'points', score: '105.50', possible: '100', letter: 'A' },
        { subject: 'Science', grade_format: 'letter', score: '99', possible: '', letter: 'B-' },
      ],
    });
    expect(validateReportCardFields(fields)).toEqual({});
    expect(reportCardPayload(fields, fields.client_entry_id)).toEqual({
      report_card: {
        period_type: 'semester', period_number: 2, school_year: 2025,
        subjects: [
          { subject: 'Math', grade_format: 'percentage', score: '0' },
          { subject: 'Art', grade_format: 'points', score: '105.50', possible: '100' },
          { subject: 'Science', grade_format: 'letter', letter: 'B-' },
        ],
      },
      reflection: '', occurred_on: '2026-01-01', is_private: true,
      client_entry_id: fields.client_entry_id,
    });
    expect(reportCardPayload(fields)).not.toHaveProperty('client_entry_id');
  });

  it.each([
    [{ period_type: 'trimester' }, 'period_type'],
    [{ period_number: '5' }, 'period_number'],
    [{ period_type: 'semester', period_number: '3' }, 'period_number'],
    [{ school_year: '' }, 'school_year'], [{ school_year: '1.5' }, 'school_year'],
    [{ school_year: '0' }, 'school_year'], [{ school_year: '9999' }, 'school_year'],
    [{ subjects: [] }, 'subjects'],
    [{ subjects: Array.from({ length: 31 }, () => draft().subjects[0]) }, 'subjects'],
    [{ occurred_on: '2026-02-30' }, 'occurred_on'],
    [{ occurred_on: '2027-01-01' }, 'occurred_on'],
  ])('validates %j at its field', (overrides, field) => {
    expect(validateReportCardFields(draft(overrides), '2026-10-13')[field]).toBeTruthy();
  });

  it('identifies each invalid subject row and duplicate class name', () => {
    const errors = validateReportCardFields(draft({ subjects: [
      { subject: 'Math', grade_format: 'percentage', score: '101' },
      { subject: ' math ', grade_format: 'points', score: '10', possible: '0' },
      { subject: '', grade_format: 'letter', letter: 'Z' },
    ] }));
    expect(errors['subjects.0.score']).toMatch(/percentage/);
    expect(errors['subjects.1.subject']).toMatch(/once/);
    expect(errors['subjects.1.possible']).toMatch(/greater than zero/);
    expect(errors['subjects.2.subject']).toBeTruthy();
    expect(errors['subjects.2.letter']).toBeTruthy();
  });
});

describe('report card device drafts', () => {
  it('separates accounts, corrections and individual grade drafts, storing only capture fields', () => {
    const fields = draft({ token: 'secret-token' });
    fields.subjects[0].password = 'secret-password';
    fields.pending = { method: 'post', payload: { ...reportCardPayload(fields, fields.client_entry_id), token: 'secret' } };
    expect(storeReportCardDraft(1, fields)).toBe(true);
    expect(readReportCardDraft(1)).toMatchObject({ subjects: [{ score: '0' }], pending: { method: 'post' } });
    expect(localStorage.getItem(reportCardDraftKey(1))).not.toMatch(/secret|password|token/);
    expect(readReportCardDraft(2)).toBeNull();
    const correction = draft({ mode: 'edit', entry_id: 9, baseline: draft() });
    storeReportCardDraft(1, correction);
    expect(readReportCardDraft(1, 'edit', 9).baseline.subjects).toEqual(draft().subjects);
    expect(readReportCardDraft(1, 'edit', 10)).toBeNull();
    const grade = {
      mode: 'create', entry_id: null, client_entry_id: newGradeRequestId(),
      subject: 'History', assessment: 'Quiz', grade_format: 'letter',
      score: '', possible: '', letter: 'A', reflection: '', occurred_on: '2026-01-01', is_private: true, pending: null,
    };
    storeGradeDraft(1, grade);
    expect(reportCardDraftKey(1)).not.toBe(gradeDraftKey(1));
    clearReportCardDraft(1, fields);
    expect(localStorage.getItem(gradeDraftKey(1))).not.toBeNull();
  });

  it('retains unfinished subjects but rejects an invalid immutable save', () => {
    const fields = draft({ subjects: [{ subject: '', grade_format: 'percentage', score: 'oops', possible: '', letter: '' }] });
    storeReportCardDraft(1, fields);
    expect(readReportCardDraft(1).subjects[0].score).toBe('oops');
    fields.pending = { method: 'post', payload: reportCardPayload(fields, fields.client_entry_id) };
    storeReportCardDraft(1, fields);
    expect(readReportCardDraft(1)).toBeNull();
  });

  it.each(['identity', 'extra field', 'different subject', 'target', 'privacy', 'period'])('rejects a corrupt %s in a saved request', (corruption) => {
    const fields = draft();
    storeReportCardDraft(1, fields);
    const raw = JSON.parse(localStorage.getItem(reportCardDraftKey(1)));
    raw.pending = { method: 'post', payload: reportCardPayload(fields, fields.client_entry_id) };
    if (corruption === 'identity') raw.pending.payload.client_entry_id = newGradeRequestId();
    if (corruption === 'extra field') raw.pending.payload.report_card.subjects[0].possible = '100';
    if (corruption === 'different subject') raw.pending.payload.report_card.subjects[0].subject = 'Art';
    if (corruption === 'target') raw.pending = { method: 'patch', entry_id: 9, payload: reportCardPayload(fields) };
    if (corruption === 'privacy') raw.is_private = 'false';
    if (corruption === 'period') raw.pending.payload.report_card.period_number = 4;
    localStorage.setItem(reportCardDraftKey(1), JSON.stringify(raw));
    expect(readReportCardDraft(1)).toBeNull();
  });

  it('preserves another tab\'s new subject and reports unavailable browser storage', () => {
    const original = draft();
    const newer = draft({ ...original, subjects: [{ ...original.subjects[0], score: '90' }] });
    storeReportCardDraft(1, newer);
    clearReportCardDraft(1, original);
    expect(readReportCardDraft(1).subjects[0].score).toBe('90');
    clearReportCardDraft(1, newer);
    expect(readReportCardDraft(1)).toBeNull();
    expect(storeReportCardDraft(null, original)).toBe(false);
    localStorage.setItem(reportCardDraftKey(1), 'not-json');
    expect(readReportCardDraft(1)).toBeNull();
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota'); });
    try { expect(storeReportCardDraft(1, original)).toBe(false); } finally { storage.mockRestore(); }
  });
});
