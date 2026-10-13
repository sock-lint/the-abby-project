import { toISODate } from '../../utils/dates';
import { GRADE_LETTERS, validateGradeFields } from './gradeDraft';

const PREFIX = 'abby:report-card-draft:v1:';
const UUID = /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i;
const FORM_FIELDS = ['period_type', 'period_number', 'school_year', 'subjects', 'reflection', 'occurred_on', 'is_private'];
const SUBJECT_FIELDS = ['subject', 'grade_format', 'score', 'possible', 'letter'];
export const MAX_REPORT_CARD_SUBJECTS = 30;

export function reportCardDraftKey(userId, mode = 'create', entryId) {
  if (!Number.isInteger(userId) || userId <= 0) return null;
  if (mode === 'edit' && (!Number.isInteger(entryId) || entryId <= 0)) return null;
  return `${PREFIX}${userId}:${mode === 'edit' ? entryId : 'new'}`;
}

export function validateReportCardFields(fields, today = toISODate(new Date())) {
  const errors = {};
  if (!['quarter', 'semester'].includes(fields.period_type)) errors.period_type = 'Choose a quarter or semester.';
  const maxPeriod = fields.period_type === 'semester' ? 2 : 4;
  if (!/^[1-4]$/.test(String(fields.period_number)) || Number(fields.period_number) > maxPeriod) {
    errors.period_number = `Choose a ${fields.period_type === 'semester' ? 'semester from 1 to 2' : 'quarter from 1 to 4'}.`;
  }
  if (!/^\d{1,4}$/.test(String(fields.school_year)) || Number(fields.school_year) < 1 || Number(fields.school_year) > 9998) {
    errors.school_year = 'Enter the school year starting year, from 1 to 9998.';
  }
  const common = validateGradeFields({
    subject: 'Report card', assessment: 'Report card', grade_format: 'letter', letter: 'P',
    reflection: fields.reflection, occurred_on: fields.occurred_on, is_private: fields.is_private,
  }, today);
  Object.assign(errors, common);
  if (!Array.isArray(fields.subjects) || fields.subjects.length < 1 || fields.subjects.length > MAX_REPORT_CARD_SUBJECTS) {
    errors.subjects = `Add between 1 and ${MAX_REPORT_CARD_SUBJECTS} subjects.`;
  } else {
    const names = new Set();
    fields.subjects.forEach((row, index) => {
      const rowErrors = validateGradeFields({
        ...row, assessment: 'Report card', reflection: '', occurred_on: fields.occurred_on, is_private: true,
      }, today);
      for (const field of SUBJECT_FIELDS) {
        if (rowErrors[field]) errors[`subjects.${index}.${field}`] = rowErrors[field];
      }
      const name = row.subject?.trim().toLocaleLowerCase();
      if (name && names.has(name)) errors[`subjects.${index}.subject`] = 'Add each subject only once per report card.';
      if (name) names.add(name);
    });
  }
  return errors;
}

function subjectPayload(row) {
  const result = { subject: row.subject.trim(), grade_format: row.grade_format };
  if (row.grade_format === 'letter') result.letter = row.letter;
  else {
    result.score = row.score.trim();
    if (row.grade_format === 'points') result.possible = row.possible.trim();
  }
  return result;
}

export function reportCardPayload(fields, clientEntryId) {
  const payload = {
    report_card: {
      period_type: fields.period_type, period_number: Number(fields.period_number), school_year: Number(fields.school_year),
      subjects: fields.subjects.map(subjectPayload),
    },
    reflection: fields.reflection, occurred_on: fields.occurred_on, is_private: fields.is_private,
  };
  if (clientEntryId) payload.client_entry_id = clientEntryId;
  return payload;
}

function captureFields(source) {
  return {
    ...Object.fromEntries(FORM_FIELDS.filter((field) => field !== 'subjects').map((field) => [field, source[field]])),
    subjects: source.subjects.map((row) => Object.fromEntries(SUBJECT_FIELDS.map((field) => [field, row[field]]))),
  };
}

function schemaValidFields(fields) {
  return fields && ['period_number', 'school_year', 'reflection', 'occurred_on'].every((field) => typeof fields[field] === 'string')
    && fields.period_number.length <= 1 && fields.school_year.length <= 4 && fields.reflection.length <= 4000
    && fields.occurred_on.length <= 10 && typeof fields.is_private === 'boolean'
    && ['quarter', 'semester'].includes(fields.period_type)
    && Array.isArray(fields.subjects) && fields.subjects.length >= 1 && fields.subjects.length <= MAX_REPORT_CARD_SUBJECTS
    && fields.subjects.every((row) => row && ['subject', 'score', 'possible', 'letter'].every((field) => typeof row[field] === 'string')
      && row.subject.length <= 80 && row.score.length <= 32 && row.possible.length <= 32
      && ['percentage', 'points', 'letter'].includes(row.grade_format)
      && (row.letter === '' || GRADE_LETTERS.includes(row.letter)));
}

function exactFields(object, names) {
  return object && typeof object === 'object' && !Array.isArray(object)
    && Object.keys(object).length === names.length && names.every((field) => field in object);
}

function validPending(pending, draft) {
  if (!pending) return pending === null;
  if (!['post', 'patch'].includes(pending.method)) return false;
  if (pending.method === 'patch' && (draft.mode !== 'edit' || pending.entry_id !== draft.entry_id)) return false;
  if (pending.method === 'post' && (draft.mode !== 'create' || pending.payload?.client_entry_id !== draft.client_entry_id)) return false;
  const fields = ['report_card', 'reflection', 'occurred_on', 'is_private', ...(pending.method === 'post' ? ['client_entry_id'] : [])];
  const payload = pending.payload;
  if (!exactFields(payload, fields)
    || !exactFields(payload.report_card, ['period_type', 'period_number', 'school_year', 'subjects'])
    || !Array.isArray(payload.report_card.subjects)) return false;
  for (const row of payload.report_card.subjects) {
    const active = row.grade_format === 'letter' ? ['letter'] : row.grade_format === 'points' ? ['score', 'possible'] : ['score'];
    if (!exactFields(row, ['subject', 'grade_format', ...active])) return false;
  }
  if (Object.keys(validateReportCardFields(draft)).length) return false;
  return JSON.stringify(reportCardPayload(draft, pending.method === 'post' ? draft.client_entry_id : undefined)) === JSON.stringify(payload);
}

export function readReportCardDraft(userId, mode = 'create', entryId) {
  const key = reportCardDraftKey(userId, mode, entryId);
  if (!key) return null;
  try {
    const draft = JSON.parse(localStorage.getItem(key));
    if (draft?.version !== 1 || draft.mode !== mode || !UUID.test(draft.client_entry_id)
      || (mode === 'edit' && draft.entry_id !== entryId) || !schemaValidFields(draft)
      || !validPending(draft.pending, draft)) return null;
    return {
      version: 1, mode, entry_id: mode === 'edit' ? entryId : null,
      client_entry_id: draft.client_entry_id, ...captureFields(draft),
      ...(mode === 'edit' && schemaValidFields(draft.baseline) ? { baseline: captureFields(draft.baseline) } : {}),
      pending: draft.pending ? {
        method: draft.pending.method, ...(mode === 'edit' ? { entry_id: entryId } : {}),
        payload: reportCardPayload(draft, mode === 'create' ? draft.client_entry_id : undefined),
      } : null,
    };
  } catch {
    return null;
  }
}

function pendingFields(payload) {
  return {
    ...payload, ...payload.report_card,
    subjects: payload.report_card.subjects.map((row) => ({ score: '', possible: '', letter: '', ...row })),
  };
}

export function storeReportCardDraft(userId, draft) {
  const key = reportCardDraftKey(userId, draft.mode, draft.entry_id);
  if (!key) return false;
  try {
    const safe = {
      version: 1, mode: draft.mode, entry_id: draft.mode === 'edit' ? draft.entry_id : null,
      client_entry_id: draft.client_entry_id, ...captureFields(draft),
      ...(draft.mode === 'edit' && !draft.needsDraftReview && schemaValidFields(draft.baseline) ? { baseline: captureFields(draft.baseline) } : {}),
      pending: draft.pending ? {
        method: draft.pending.method, ...(draft.mode === 'edit' ? { entry_id: draft.entry_id } : {}),
        payload: reportCardPayload(pendingFields(draft.pending.payload), draft.mode === 'create' ? draft.client_entry_id : undefined),
      } : null,
    };
    localStorage.setItem(key, JSON.stringify(safe));
    return true;
  } catch {
    return false;
  }
}

export function clearReportCardDraft(userId, savedDraft) {
  const key = reportCardDraftKey(userId, savedDraft.mode, savedDraft.entry_id);
  if (!key) return;
  try {
    const current = readReportCardDraft(userId, savedDraft.mode, savedDraft.entry_id);
    if (current?.client_entry_id !== savedDraft.client_entry_id
      || FORM_FIELDS.some((field) => JSON.stringify(current?.[field]) !== JSON.stringify(savedDraft[field]))) return;
    localStorage.removeItem(key);
  } catch {
    // A confirmed server report card remains available if device cleanup fails.
  }
}
