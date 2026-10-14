import { useRef, useState } from 'react';
import { Check, Heart, Lock, PawPrint, Plus } from 'lucide-react';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import GradeRecordDetails from '../../components/chronicle/GradeRecordDetails';
import { SelectField, TextAreaField, TextField } from '../../components/form';
import { useRole } from '../../hooks/useRole';
import { publishChronicleChange } from '../../hooks/useChronicleRevision';
import { updateGradeEntry, writeGrade } from '../../api';
import { fieldErrors } from '../../utils/api';
import { toISODate } from '../../utils/dates';
import { formatDate } from '../../utils/format';
import { GRADE_LETTERS, newGradeRequestId } from './gradeDraft';
import {
  clearReportCardDraft, MAX_REPORT_CARD_SUBJECTS, readReportCardDraft, reportCardPayload,
  storeReportCardDraft, validateReportCardFields,
} from './reportCardDraft';

function emptySubject() {
  return { subject: '', grade_format: 'percentage', score: '', possible: '', letter: '' };
}

function initialForm(userId, mode, entry) {
  const report = entry?.metadata?.report_card ?? {};
  const now = new Date();
  const baseline = {
    period_type: report.period_type || 'quarter', period_number: String(report.period_number ?? 1),
    school_year: String(report.school_year ?? (now.getMonth() >= 7 ? now.getFullYear() : now.getFullYear() - 1)),
    subjects: report.subjects?.length ? report.subjects.map((row) => ({
      subject: row.subject || '', grade_format: row.grade_format || 'percentage',
      score: String(row.score ?? ''), possible: String(row.possible ?? ''), letter: row.letter || '',
    })) : [emptySubject()],
    reflection: entry?.summary || '', occurred_on: entry?.occurred_on || toISODate(now),
    is_private: entry?.is_private ?? true,
  };
  const pendingCreate = readReportCardDraft(userId);
  const draft = pendingCreate?.pending?.method === 'post' && pendingCreate.client_entry_id === entry?.client_entry_id
    ? pendingCreate : readReportCardDraft(userId, mode, entry?.id);
  const restored = { ...draft };
  if (mode === 'edit' && draft?.baseline && !draft.pending) {
    const periodFields = ['period_type', 'period_number', 'school_year'];
    const changedPeriod = periodFields.some((field) => draft[field] !== draft.baseline[field]);
    for (const field of Object.keys(baseline)) {
      // A reporting period and the subjects array each stay together, so a
      // restored correction cannot combine grades with a different saved term.
      if (changedPeriod && periodFields.includes(field)) continue;
      if (JSON.stringify(draft[field]) === JSON.stringify(draft.baseline[field])) restored[field] = baseline[field];
    }
  }
  return {
    mode, entry_id: mode === 'edit' ? entry?.id : null, client_entry_id: newGradeRequestId(),
    ...baseline, pending: null, ...restored, baseline, restored: Boolean(draft),
    needsDraftReview: mode === 'edit' && Boolean(draft) && !draft.baseline && !draft.pending,
  };
}

function reportFieldErrors(err) {
  const result = fieldErrors(err);
  const report = err?.response?.report_card;
  if (!report || typeof report !== 'object') return result;
  for (const field of ['period_type', 'period_number', 'school_year', 'non_field_errors']) {
    const message = Array.isArray(report[field]) ? report[field][0] : report[field];
    if (typeof message === 'string') result[field === 'non_field_errors' ? 'subjects' : field] = message;
  }
  if (report.subjects && typeof report.subjects === 'object') {
    Object.entries(report.subjects).forEach(([index, row]) => {
      if (typeof row === 'string') { result.subjects = row; return; }
      if (!row || typeof row !== 'object') return;
      for (const [field, value] of Object.entries(row)) {
        const message = Array.isArray(value) ? value[0] : value;
        if (typeof message === 'string') result[`subjects.${index}.${field === 'non_field_errors' ? 'subject' : field}`] = message;
      }
    });
  }
  return result;
}

async function saveWithDeadline(request) {
  let timer;
  try {
    return await Promise.race([
      request(),
      new Promise((_, reject) => {
        timer = window.setTimeout(() => reject(new Error('The connection took too long.')), 20000);
      }),
    ]);
  } finally {
    window.clearTimeout(timer);
  }
}

export default function ReportCardFormModal(props) {
  const { user } = useRole();
  return (
    <ReportCardForm
      key={`${user?.id ?? 'anonymous'}:${props.mode ?? 'create'}:${props.entry?.id ?? 'new'}`}
      {...props} userId={user?.id}
    />
  );
}

function ReportCardForm({ mode = 'create', entry, userId, onSaved, onClose }) {
  const [form, setForm] = useState(() => initialForm(userId, mode, entry));
  const formRef = useRef(form);
  const inFlight = useRef(false);
  const finished = useRef(false);
  const [storageState, setStorageState] = useState(form.restored ? 'saved' : 'idle');
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState({});
  const [error, setError] = useState('');
  const [savedEntry, setSavedEntry] = useState(null);
  const blocked = saving || Boolean(form.pending);
  const hasChanges = Object.keys(form.baseline).some((field) => JSON.stringify(form[field]) !== JSON.stringify(form.baseline[field]));
  const dirty = hasChanges && storageState !== 'saved' && !savedEntry;
  const today = toISODate(new Date());

  const changeForm = (changes) => {
    const next = { ...formRef.current, ...changes };
    formRef.current = next;
    setStorageState(storeReportCardDraft(userId, next) ? 'saved' : 'unavailable');
    setForm(next);
    setErrors((previous) => Object.fromEntries(Object.entries(previous)
      .filter(([field]) => !(field in changes) && !(changes.subjects && field.startsWith('subjects.')))));
    return next;
  };

  const changeSubject = (index, changes) => {
    changeForm({ subjects: formRef.current.subjects.map((row, rowIndex) => rowIndex === index ? { ...row, ...changes } : row) });
  };

  const submit = async (event) => {
    event.preventDefault();
    if (inFlight.current) return;
    const current = formRef.current;
    if (!current.pending) {
      const validation = validateReportCardFields(current, today);
      setErrors(validation);
      if (Object.keys(validation).length) {
        setError('Check the highlighted fields before saving.');
        return;
      }
    }
    const request = current.pending ?? {
      method: current.mode === 'edit' ? 'patch' : 'post',
      ...(current.mode === 'edit' ? { entry_id: current.entry_id } : {}),
      payload: reportCardPayload(current, current.mode === 'create' ? current.client_entry_id : undefined),
    };
    // Save the exact submission before sending. An uncertain save always
    // retries this request, rather than creating another report card/reward.
    changeForm({ pending: request });
    inFlight.current = true;
    setSaving(true);
    setError('');
    setErrors({});
    try {
      const result = await saveWithDeadline(() => request.method === 'post'
        ? writeGrade(request.payload) : updateGradeEntry(request.entry_id, request.payload));
      clearReportCardDraft(userId, current);
      setSavedEntry(result);
    } catch (err) {
      if (err?.status >= 400 && err?.status < 500) {
        changeForm({ pending: null });
        const fields = reportFieldErrors(err);
        setErrors(fields);
        const detail = err.response?.detail || err.response?.error;
        setError(Object.keys(fields).length ? 'Check the highlighted fields.'
          : typeof detail === 'string' ? detail : 'Could not save this report card. Review your entries and try again.');
      } else {
        setError('We could not confirm the save. Check save when your connection returns to safely finish saving this report card.');
      }
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  };

  const finish = () => {
    if (finished.current) return;
    finished.current = true;
    onSaved?.(savedEntry);
    onClose?.();
    publishChronicleChange(savedEntry.user);
  };

  if (savedEntry) {
    const receipt = savedEntry.reward_receipt;
    const isCreate = form.mode === 'create';
    const awarded = isCreate && receipt?.status === 'awarded' && Number.isFinite(receipt.xp_awarded) && receipt.xp_awarded > 0;
    return (
      <BottomSheet title={isCreate ? 'Report card saved' : 'Report card corrected'} onClose={finish}>
        <div className="space-y-4 text-center">
          <div className="flex justify-center text-sheikah-teal-deep" aria-hidden="true">
            {awarded ? <PawPrint size={48} className="animate-rune-pulse" /> : <Check size={48} />}
          </div>
          <div role="status" aria-live="polite" className="space-y-2">
            <p className="font-display text-lede text-ink-primary">{isCreate ? 'Your report card is in your history.' : 'Your report card has been updated.'}</p>
            {awarded && <p className="font-semibold text-body text-sheikah-teal-deep">+{receipt.xp_awarded} XP earned</p>}
            {isCreate && receipt?.status === 'daily_limit' && <p className="text-body text-ink-secondary">You already earned recognition for tracking a grade or report card today. This report card is still saved in your history.</p>}
            {isCreate && receipt?.status === 'unavailable' && <p className="text-body text-ink-secondary">Your report card is saved. Its reward could not be confirmed.</p>}
            {isCreate && receipt?.status === 'not_eligible' && <p className="text-body text-ink-secondary">This report card is saved without an extra reward.</p>}
            {!isCreate && <p className="text-body text-ink-secondary">Corrections do not earn another reward.</p>}
          </div>
          <GradeRecordDetails entry={savedEntry} />
          <p className="text-body text-ink-secondary">{savedEntry.is_private === false ? 'Shared with parents in your family. They can leave a response.' : 'Only you can read this report card in the app.'}</p>
          <Button variant="primary" className="w-full" onClick={finish}>Done</Button>
        </div>
      </BottomSheet>
    );
  }

  return (
    <BottomSheet title={form.mode === 'edit' ? 'Correct report card' : 'Add a report card'} onClose={onClose} disabled={saving} dirty={dirty}>
      <form onSubmit={submit} noValidate className="space-y-4">
        <p className="text-body text-ink-secondary">Save the grades on your school report card together. Each subject can use its own recorded grade format.</p>
        {form.needsDraftReview && (
          <section aria-label="Latest saved report card" className="rounded-lg border border-ink-page-shadow p-3 space-y-3">
            <p className="text-body">An older correction draft was restored. Review it against the latest saved report card below before saving.</p>
            <GradeRecordDetails entry={entry} />
            <p className="text-caption">{formatDate(entry.occurred_on)} · {entry.is_private === false ? 'Shared with parents' : 'Only me'}</p>
            {entry.summary && <p className="text-body whitespace-pre-wrap break-words">{entry.summary}</p>}
          </section>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SelectField label="Reporting period" value={form.period_type} disabled={blocked} error={errors.period_type} onChange={(event) => changeForm({ period_type: event.target.value, period_number: String(Math.min(Number(form.period_number) || 1, event.target.value === 'semester' ? 2 : 4)) })}>
            <option value="quarter">Quarter</option><option value="semester">Semester</option>
          </SelectField>
          <SelectField label={form.period_type === 'semester' ? 'Semester' : 'Quarter'} value={form.period_number} disabled={blocked} error={errors.period_number} onChange={(event) => changeForm({ period_number: event.target.value })}>
            {Array.from({ length: form.period_type === 'semester' ? 2 : 4 }, (_, index) => <option key={index + 1} value={index + 1}>{index + 1}</option>)}
          </SelectField>
        </div>
        <TextField label="School year starting year" type="text" inputMode="numeric" maxLength={4} value={form.school_year} disabled={blocked} error={errors.school_year} helpText="For 2025–2026, enter 2025." onChange={(event) => changeForm({ school_year: event.target.value })} />
        <section aria-label="Report card subjects" className="space-y-3">
          <p className="text-body text-ink-secondary">Add 1–{MAX_REPORT_CARD_SUBJECTS} subjects as shown on your report card.</p>
          {errors.subjects && <p role="alert" className="text-body text-ember-deep">{errors.subjects}</p>}
          {form.subjects.map((row, index) => (
            <fieldset key={index} className="rounded-lg border border-ink-page-shadow p-3 space-y-3">
              <legend className="px-1 font-semibold text-body text-ink-primary">Subject {index + 1}</legend>
              <TextField label="Subject or class" value={row.subject} maxLength={80} disabled={blocked} error={errors[`subjects.${index}.subject`]} onChange={(event) => changeSubject(index, { subject: event.target.value })} />
              <SelectField label="Grade format" value={row.grade_format} disabled={blocked} error={errors[`subjects.${index}.grade_format`]} onChange={(event) => changeSubject(index, { grade_format: event.target.value })}>
                <option value="percentage">Percentage</option><option value="points">Points</option><option value="letter">Letter</option>
              </SelectField>
              {row.grade_format === 'letter' ? (
                <SelectField label="Letter grade" value={row.letter} disabled={blocked} error={errors[`subjects.${index}.letter`]} onChange={(event) => changeSubject(index, { letter: event.target.value })}>
                  <option value="">Choose the recorded grade</option>
                  {GRADE_LETTERS.map((letter) => <option key={letter} value={letter}>{letter}</option>)}
                </SelectField>
              ) : (
                <div className={row.grade_format === 'points' ? 'grid grid-cols-1 sm:grid-cols-2 gap-3' : ''}>
                  <TextField label={row.grade_format === 'points' ? 'Points earned' : 'Percentage'} type="text" inputMode="decimal" maxLength={32} value={row.score} disabled={blocked} error={errors[`subjects.${index}.score`]} helpText={row.grade_format === 'percentage' ? 'From 0 to 100. Zero is a valid result.' : 'Extra credit can exceed the points possible.'} onChange={(event) => changeSubject(index, { score: event.target.value })} />
                  {row.grade_format === 'points' && <TextField label="Points possible" type="text" inputMode="decimal" maxLength={32} value={row.possible} disabled={blocked} error={errors[`subjects.${index}.possible`]} onChange={(event) => changeSubject(index, { possible: event.target.value })} />}
                </div>
              )}
              <Button variant="ghost" size="sm" disabled={blocked || form.subjects.length === 1} aria-label={`Remove subject ${index + 1}`} onClick={() => changeForm({ subjects: formRef.current.subjects.filter((_, rowIndex) => rowIndex !== index) })}>Remove subject</Button>
            </fieldset>
          ))}
          <Button variant="secondary" disabled={blocked || form.subjects.length >= MAX_REPORT_CARD_SUBJECTS} onClick={() => changeForm({ subjects: [...formRef.current.subjects, emptySubject()] })}><Plus size={16} aria-hidden="true" /> Add subject</Button>
        </section>
        <TextField label="Date received" type="date" value={form.occurred_on} max={today} disabled={blocked} error={errors.occurred_on} onChange={(event) => changeForm({ occurred_on: event.target.value })} />
        <TextAreaField label="Reflection (optional)" rows={3} maxLength={4000} value={form.reflection} disabled={blocked} error={errors.reflection} helpText="What would you like to remember about this quarter or semester?" onChange={(event) => changeForm({ reflection: event.target.value })} />
        {/* intentional: the enclosing checkbox label supplies an accessible
            name and touch target outside the text/select primitives. */}
        <label className="flex items-center gap-3 min-h-11 text-body text-ink-primary">
          <input type="checkbox" checked={!form.is_private} disabled={blocked} className="h-5 w-5 shrink-0 accent-sheikah-teal-deep" onChange={(event) => changeForm({ is_private: !event.target.checked })} />
          Share with parents in my family
        </label>
        {errors.is_private && <p role="alert" className="text-body text-ember-deep">{errors.is_private}</p>}
        <p className="flex items-start gap-2 text-caption text-ink-secondary">
          {form.is_private ? <Lock size={14} aria-hidden="true" /> : <Heart size={14} aria-hidden="true" />}
          <span>{form.is_private ? 'Only you can read this report card in the app.' : 'Parents in your family can read this report card and leave a response.'}</span>
        </p>
        <ErrorAlert message={error} />
        <p role="status" aria-live="polite" className="text-caption text-ink-whisper">
          {saving ? 'Saving this report card to your history…'
            : form.pending ? 'Save not confirmed yet. Check save to safely try again.'
              : storageState === 'saved' ? 'Draft kept on this device. It is not in your history yet.'
                : storageState === 'unavailable' ? 'This browser cannot keep a draft. Keep this window open until you save.'
                  : 'Save when you are ready to keep this report card.'}
        </p>
        {storageState === 'unavailable' && form.pending && <p className="text-caption text-ember-deep">This browser cannot keep a draft. Keep this window open until the save is confirmed.</p>}
        <div className="flex flex-wrap justify-end gap-2">
          {!dirty && <Button variant="ghost" onClick={onClose} disabled={saving}>{storageState === 'saved' && hasChanges ? 'Keep draft & close' : 'Close'}</Button>}
          <Button type="submit" loading={saving}>{form.pending ? 'Check save' : form.mode === 'edit' ? 'Save correction' : 'Save report card'}</Button>
        </div>
      </form>
    </BottomSheet>
  );
}
