import { beforeEach, describe, expect, it, vi } from 'vitest';
import { HttpResponse } from 'msw';
import { act, renderWithProviders, screen, within } from '../../test/render';
import { buildUser } from '../../test/factories';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { toISODate } from '../../utils/dates';
import * as chronicleApi from '../../api';
import ReportCardFormModal from './ReportCardFormModal';
import { newGradeRequestId } from './gradeDraft';
import { readReportCardDraft, reportCardPayload, storeReportCardDraft } from './reportCardDraft';

const role = vi.hoisted(() => ({ user: null }));
vi.mock('../../hooks/useRole.js', () => ({ useRole: () => ({ user: role.user }) }));
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

beforeEach(() => { role.user = buildUser(); });

function savedReport(payload, overrides = {}) {
  return {
    id: 60, user: 1, kind: 'grade', occurred_on: payload.occurred_on,
    summary: payload.reflection, is_private: payload.is_private,
    client_entry_id: payload.client_entry_id, metadata: { report_card: payload.report_card },
    reward_receipt: { status: 'awarded', xp_awarded: 10 }, ...overrides,
  };
}

function draft(overrides = {}) {
  return {
    mode: 'create', entry_id: null, client_entry_id: newGradeRequestId(),
    period_type: 'quarter', period_number: '1', school_year: '2025',
    subjects: [{ subject: 'Math', grade_format: 'percentage', score: '82.5', possible: '', letter: '' }],
    reflection: '', occurred_on: '2026-01-01', is_private: true, pending: null, ...overrides,
  };
}

function mount(props = {}) {
  return renderWithProviders(<ReportCardFormModal onClose={() => {}} {...props} />, { withAuth: false });
}

function row(number = 1) { return within(screen.getByRole('group', { name: `Subject ${number}` })); }

async function completeBasics(user, score = '82.5') {
  await user.type(row().getByRole('textbox', { name: 'Subject or class' }), 'Math');
  await user.type(row().getByRole('textbox', { name: 'Percentage' }), score);
  await user.clear(screen.getByRole('textbox', { name: 'School year starting year' }));
  await user.type(screen.getByRole('textbox', { name: 'School year starting year' }), '2025');
}

describe('ReportCardFormModal', () => {
  it('starts with a private quarter report card and a subject using the original recorded grade', () => {
    mount();
    expect(screen.getByRole('dialog', { name: 'Add a report card' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Reporting period' })).toHaveValue('quarter');
    expect(screen.getByRole('combobox', { name: 'Quarter' })).toHaveValue('1');
    expect(screen.getByLabelText('Date received')).toHaveValue(toISODate(new Date()));
    expect(row().getByRole('combobox', { name: 'Grade format' })).toHaveValue('percentage');
    expect(screen.getByRole('checkbox', { name: 'Share with parents in my family' })).not.toBeChecked();
    expect(screen.getByRole('button', { name: 'Remove subject 1' })).toBeDisabled();
  });

  it('saves a quarter, school year and zero score with its stable identity and confirms exact receipt XP', async () => {
    const spy = spyHandler('post', /\/api\/chronicle\/grades\/$/, ({ body }) => savedReport(body, { reward_receipt: { status: 'awarded', xp_awarded: 20 } }));
    server.use(spy.handler);
    const onSaved = vi.fn();
    const onClose = vi.fn();
    const { user } = mount({ onSaved, onClose });
    await completeBasics(user, '0');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Quarter' }), '4');
    const stored = readReportCardDraft(1);
    await user.click(screen.getByRole('button', { name: 'Save report card' }));
    await screen.findByText('+20 XP earned');
    expect(spy.calls).toHaveLength(1);
    expect(spy.calls[0].url).toMatch(/\/api\/chronicle\/grades\/$/);
    expect(spy.calls[0].body).toEqual({
      report_card: { period_type: 'quarter', period_number: 4, school_year: 2025, subjects: [{ subject: 'Math', grade_format: 'percentage', score: '0' }] },
      reflection: '', occurred_on: toISODate(new Date()), is_private: true, client_entry_id: stored.client_entry_id,
    });
    expect(readReportCardDraft(1)).toBeNull();
    expect(onSaved).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: 60 }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('adds and removes subjects and saves mixed formats for a shared semester report card', async () => {
    const spy = spyHandler('post', /\/api\/chronicle\/grades\/$/, ({ body }) => savedReport(body));
    server.use(spy.handler);
    const { user } = mount();
    await completeBasics(user);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Quarter' }), '4');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Reporting period' }), 'semester');
    expect(screen.getByRole('combobox', { name: 'Semester' })).toHaveValue('2');
    expect(within(screen.getByRole('combobox', { name: 'Semester' })).getAllByRole('option')).toHaveLength(2);
    await user.click(screen.getByRole('button', { name: 'Add subject' }));
    await user.type(row(2).getByRole('textbox', { name: 'Subject or class' }), 'Science');
    await user.selectOptions(row(2).getByRole('combobox', { name: 'Grade format' }), 'letter');
    await user.selectOptions(row(2).getByRole('combobox', { name: 'Letter grade' }), 'B-');
    await user.click(screen.getByRole('button', { name: 'Add subject' }));
    await user.type(row(3).getByRole('textbox', { name: 'Subject or class' }), 'Art');
    await user.selectOptions(row(3).getByRole('combobox', { name: 'Grade format' }), 'points');
    await user.type(row(3).getByRole('textbox', { name: 'Points earned' }), '105.5');
    await user.type(row(3).getByRole('textbox', { name: 'Points possible' }), '100');
    await user.click(screen.getByRole('button', { name: 'Add subject' }));
    await user.click(screen.getByRole('button', { name: 'Remove subject 4' }));
    await user.clear(screen.getByLabelText('Date received'));
    await user.type(screen.getByLabelText('Date received'), '2026-01-02');
    await user.type(screen.getByRole('textbox', { name: 'Reflection (optional)' }), 'A lot of practice this semester.');
    await user.click(screen.getByRole('checkbox', { name: 'Share with parents in my family' }));
    await user.click(screen.getByRole('button', { name: 'Save report card' }));
    await screen.findByRole('dialog', { name: 'Report card saved' });
    expect(spy.calls[0].body).toMatchObject({
      report_card: { period_type: 'semester', period_number: 2, school_year: 2025, subjects: [
        { subject: 'Math', grade_format: 'percentage', score: '82.5' },
        { subject: 'Science', grade_format: 'letter', letter: 'B-' },
        { subject: 'Art', grade_format: 'points', score: '105.5', possible: '100' },
      ] },
      reflection: 'A lot of practice this semester.', occurred_on: '2026-01-02', is_private: false,
    });
    expect(screen.getByText(/Shared with parents in your family/i)).toBeInTheDocument();
  });

  it('validates required fields and duplicate subjects without sending an invalid card', async () => {
    const spy = spyHandler('post', /\/api\/chronicle\/grades\/$/, {});
    server.use(spy.handler);
    const { user } = mount();
    await user.click(screen.getByRole('button', { name: 'Save report card' }));
    expect(row().getByRole('textbox', { name: 'Subject or class' })).toHaveAttribute('aria-invalid', 'true');
    expect(row().getByRole('textbox', { name: 'Percentage' })).toHaveAttribute('aria-invalid', 'true');
    await completeBasics(user);
    await user.click(screen.getByRole('button', { name: 'Add subject' }));
    await user.type(row(2).getByRole('textbox', { name: 'Subject or class' }), ' math ');
    await user.type(row(2).getByRole('textbox', { name: 'Percentage' }), '101');
    await user.click(screen.getByRole('button', { name: 'Save report card' }));
    expect(row(2).getByRole('textbox', { name: 'Subject or class' })).toHaveAttribute('aria-invalid', 'true');
    expect(row(2).getByText(/each subject only once/i)).toBeInTheDocument();
    expect(row(2).getByText(/percentage between 0 and 100/i)).toBeInTheDocument();
    expect(spy.calls).toHaveLength(0);
  });

  it('allows at most 30 rows and keeps the original rows when removing a middle subject', async () => {
    const subjects = Array.from({ length: 30 }, (_, index) => ({ ...draft().subjects[0], subject: `Class ${index + 1}` }));
    storeReportCardDraft(1, draft({ subjects }));
    const { user } = mount();
    expect(screen.getAllByRole('group', { name: /^Subject \d+$/ })).toHaveLength(30);
    expect(screen.getByRole('button', { name: 'Add subject' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Remove subject 2' }));
    expect(row(2).getByRole('textbox', { name: 'Subject or class' })).toHaveValue('Class 3');
    expect(screen.getByRole('button', { name: 'Add subject' })).toBeEnabled();
    expect(readReportCardDraft(1).subjects).toHaveLength(29);
  });

  it('restores an account-specific multi-subject draft after close and isolates another account', async () => {
    const first = mount();
    await completeBasics(first.user);
    await first.user.click(screen.getByRole('button', { name: 'Add subject' }));
    await first.user.type(row(2).getByRole('textbox', { name: 'Subject or class' }), 'Science');
    await first.user.selectOptions(row(2).getByRole('combobox', { name: 'Grade format' }), 'letter');
    await first.user.selectOptions(row(2).getByRole('combobox', { name: 'Letter grade' }), 'F');
    const requestId = readReportCardDraft(1).client_entry_id;
    await first.user.click(screen.getByRole('button', { name: 'Keep draft & close' }));
    first.unmount();
    const second = mount();
    expect(row(2).getByRole('combobox', { name: 'Letter grade' })).toHaveValue('F');
    expect(readReportCardDraft(1).client_entry_id).toBe(requestId);
    role.user = buildUser({ id: 2 });
    second.rerender(<ReportCardFormModal onClose={() => {}} />);
    expect(screen.getAllByRole('group', { name: /^Subject \d+$/ })).toHaveLength(1);
    expect(row().getByRole('textbox', { name: 'Subject or class' })).toHaveValue('');
    await second.user.type(row().getByRole('textbox', { name: 'Subject or class' }), 'History');
    expect(readReportCardDraft(1).subjects[0].subject).toBe('Math');
    expect(readReportCardDraft(2).subjects[0].subject).toBe('History');
  });

  it('recovers an uncertain create through the exact original immutable request, even from edit', async () => {
    const spy = spyHandler('post', /\/api\/chronicle\/grades\/$/, ({ body }) => spy.calls.length === 1 ? HttpResponse.json({ detail: 'Temporarily unavailable.' }, { status: 503 }) : savedReport(body));
    server.use(spy.handler);
    const first = mount();
    await completeBasics(first.user);
    await first.user.click(screen.getByRole('button', { name: 'Save report card' }));
    await screen.findByText(/We could not confirm the save/i);
    expect(row().getByRole('textbox', { name: 'Percentage' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Add subject' })).toBeDisabled();
    expect(screen.queryByText(/XP earned/)).toBeNull();
    expect(readReportCardDraft(1).pending.payload).toEqual(spy.calls[0].body);
    first.unmount();
    const second = mount({ mode: 'edit', entry: savedReport(spy.calls[0].body) });
    expect(row().getByRole('textbox', { name: 'Percentage' })).toBeDisabled();
    await second.user.click(screen.getByRole('button', { name: 'Check save' }));
    await screen.findByText('+10 XP earned');
    expect(spy.calls).toHaveLength(2);
    expect(spy.calls[1].body).toEqual(spy.calls[0].body);
    expect(readReportCardDraft(1)).toBeNull();
  });

  it('keeps a stalled request retryable with its original UUID', async () => {
    const spy = vi.spyOn(chronicleApi, 'writeGrade').mockImplementationOnce(() => new Promise(() => {}))
      .mockImplementationOnce((payload) => Promise.resolve(savedReport(payload)));
    const realTimeout = window.setTimeout.bind(window);
    let deadline;
    const timerSpy = vi.spyOn(window, 'setTimeout').mockImplementation((callback, delay, ...args) => {
      if (delay === 20000) { deadline = callback; return -1; }
      return realTimeout(callback, delay, ...args);
    });
    try {
      const { user } = mount();
      await completeBasics(user);
      await user.click(screen.getByRole('button', { name: 'Save report card' }));
      await act(async () => { deadline(); });
      expect(screen.getByRole('button', { name: 'Check save' })).toBeEnabled();
      await user.click(screen.getByRole('button', { name: 'Check save' }));
      await screen.findByText('+10 XP earned');
      expect(spy.mock.calls[1][0]).toEqual(spy.mock.calls[0][0]);
    } finally { spy.mockRestore(); timerSpy.mockRestore(); }
  });

  it.each(['list', 'indexed'])('renders %s nested server errors beside period and subject controls while preserving editable values', async (shape) => {
    const spy = spyHandler('post', /\/api\/chronicle\/grades\/$/, HttpResponse.json({ report_card: {
      school_year: ['Check this school year.'], subjects: shape === 'list' ? [{ score: ['Keep this score to six decimal places.'] }] : { 0: { score: ['Keep this score to six decimal places.'] } },
    } }, { status: 400 }));
    server.use(spy.handler);
    const { user } = mount();
    await completeBasics(user);
    await user.click(screen.getByRole('button', { name: 'Save report card' }));
    await screen.findByText('Check this school year.');
    expect(row().getByText('Keep this score to six decimal places.')).toBeInTheDocument();
    expect(row().getByRole('textbox', { name: 'Percentage' })).toBeEnabled();
    expect(row().getByRole('textbox', { name: 'Percentage' })).toHaveValue('82.5');
    expect(readReportCardDraft(1).pending).toBeNull();
    expect(screen.queryByText(/\{"report_card"/)).toBeNull();
  });

  it('corrects historical report card subjects, term, date, reflection and sharing without another reward', async () => {
    const original = savedReport(reportCardPayload(draft(), draft().client_entry_id));
    const spy = spyHandler('patch', /\/api\/chronicle\/60\/grade\/$/, ({ body }) => savedReport(body));
    server.use(spy.handler);
    const { user } = mount({ mode: 'edit', entry: original });
    await user.clear(row().getByRole('textbox', { name: 'Percentage' }));
    await user.type(row().getByRole('textbox', { name: 'Percentage' }), '90');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Quarter' }), '2');
    await user.clear(screen.getByLabelText('Date received'));
    await user.type(screen.getByLabelText('Date received'), '2026-01-02');
    await user.type(screen.getByRole('textbox', { name: 'Reflection (optional)' }), 'Correction confirmed.');
    await user.click(screen.getByRole('checkbox', { name: 'Share with parents in my family' }));
    await user.click(screen.getByRole('button', { name: 'Save correction' }));
    await screen.findByRole('dialog', { name: 'Report card corrected' });
    expect(spy.calls).toHaveLength(1);
    expect(spy.calls[0].url).toMatch(/\/api\/chronicle\/60\/grade\/$/);
    expect(spy.calls[0].body).toEqual({
      report_card: { period_type: 'quarter', period_number: 2, school_year: 2025, subjects: [{ subject: 'Math', grade_format: 'percentage', score: '90' }] },
      occurred_on: '2026-01-02', reflection: 'Correction confirmed.', is_private: false,
    });
    expect(screen.queryByText(/XP earned/)).toBeNull();
    expect(screen.getByText(/Corrections do not earn another reward/)).toBeInTheDocument();
  });

  it('restores reflection edits while using newer saved subjects, term and sharing for untouched fields', () => {
    const baseline = draft();
    storeReportCardDraft(1, draft({ mode: 'edit', entry_id: 60, baseline, reflection: 'A kept thought.' }));
    const newer = savedReport(reportCardPayload(draft({ period_type: 'semester', period_number: '2', is_private: false, subjects: [{ subject: 'Math', grade_format: 'letter', score: '', possible: '', letter: 'B' }] })));
    mount({ mode: 'edit', entry: newer });
    expect(screen.getByRole('textbox', { name: 'Reflection (optional)' })).toHaveValue('A kept thought.');
    expect(screen.getByRole('combobox', { name: 'Reporting period' })).toHaveValue('semester');
    expect(row().getByRole('combobox', { name: 'Letter grade' })).toHaveValue('B');
    expect(screen.getByRole('checkbox', { name: 'Share with parents in my family' })).toBeChecked();
  });

  it.each(['daily_limit', 'unavailable', 'not_eligible'])('saves a report card with a %s receipt without claiming XP', async (status) => {
    const spy = spyHandler('post', /\/api\/chronicle\/grades\/$/, ({ body }) => savedReport(body, { reward_receipt: { status, xp_awarded: 0 } }));
    server.use(spy.handler);
    const { user } = mount();
    await completeBasics(user);
    await user.click(screen.getByRole('button', { name: 'Save report card' }));
    await screen.findByRole('dialog', { name: 'Report card saved' });
    expect(screen.queryByText(/XP earned/)).toBeNull();
    expect(readReportCardDraft(1)).toBeNull();
  });

  it('warns about unavailable storage and preserves unsent input when the form closes', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota'); });
    try {
      const { user } = mount();
      await completeBasics(user);
      expect(screen.getByText(/This browser cannot keep a draft/)).toBeInTheDocument();
      await user.click(screen.getByRole('button', { name: 'Close', exact: true }));
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
      expect(row().getByRole('textbox', { name: 'Percentage' })).toHaveValue('82.5');
    } finally { storage.mockRestore(); }
  });
});
