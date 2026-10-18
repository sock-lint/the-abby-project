import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import SubmissionTiming from './SubmissionTiming';

const snapshot = {
  version: 1, schedule: 'homework', timezone: 'America/Phoenix',
  due_on: '2026-10-16', submitted_on: '2026-10-16',
  submitted_at: '2026-10-17T01:30:00Z', timeliness: 'on_time',
};
const dateRow = (label) => screen.getByText(label, { exact: true }).parentElement;

describe('Saved submission timing', () => {
  it.each(['2026-10-20', null])('keeps the frozen deadline and timezone separate from the edited current deadline %s', (currentDue) => {
    render(<SubmissionTiming kind="homework" record={{
      timing_snapshot: snapshot, current_due_date: currentDue, timeliness: 'late',
      status: 'approved', decided_at: '2026-10-21T18:00:00Z',
    }} />);
    expect(dateRow('Due').querySelector('time')).toHaveAttribute('datetime', '2026-10-16');
    if (currentDue) expect(dateRow('Current due').querySelector('time')).toHaveAttribute('datetime', currentDue);
    else expect(dateRow('Current due')).toHaveTextContent('No due date');
    expect(dateRow('Submitted')).toHaveTextContent('Oct 16');
    expect(dateRow('Submitted')).toHaveTextContent('MST');
    expect(dateRow('Approved').querySelector('time')).toHaveAttribute('datetime', '2026-10-21T18:00:00Z');
    expect(screen.getByText('On time')).toBeInTheDocument();
    expect(screen.queryByText('Late')).not.toBeInTheDocument();
  });

  it.each(['daily', 'weekly', 'one_time'])('shows one scheduled date for a %s chore, with its actual completion timestamp', (schedule) => {
    render(<SubmissionTiming kind="chore" record={{ timing_snapshot: {
      ...snapshot, schedule, period_start: schedule === 'daily' ? '2026-10-18' : '2026-10-12', period_end: '2026-10-18', due_on: '2026-10-18',
    } }} />);
    expect(dateRow('Scheduled for').querySelector('time')).toHaveAttribute('datetime', '2026-10-18');
    expect(screen.queryByText('Due', { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText('Scheduled week')).not.toBeInTheDocument();
    expect(screen.queryByText('Current due')).not.toBeInTheDocument();
    expect(dateRow('Marked complete').querySelector('time')).toHaveAttribute('datetime', snapshot.submitted_at);
  });

  it('labels older chore timing unknown without treating the period key as its completion timestamp', () => {
    render(<SubmissionTiming kind="chore" record={{ completed_date: '2026-10-12', created_at: '2026-10-16T18:30:00Z' }} />);
    expect(dateRow('Recorded for').querySelector('time')).toHaveAttribute('datetime', '2026-10-12');
    expect(dateRow('Recorded for').closest('details')).not.toHaveAttribute('open');
    expect(dateRow('Marked complete').querySelector('time')).toHaveAttribute('datetime', '2026-10-16T18:30:00Z');
    expect(dateRow('Scheduled for')).toHaveTextContent('Not recorded');
    expect(screen.queryByText('Timing unknown')).not.toBeInTheDocument();
    expect(screen.queryByText('Due', { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText('Current due')).not.toBeInTheDocument();
    expect(screen.queryByText('On time')).not.toBeInTheDocument();
  });

  it('does not invent a submitted timestamp when only the older period date is available', () => {
    render(<SubmissionTiming kind="chore" record={{ completed_date: '2026-10-12' }} />);
    expect(dateRow('Done on')).toHaveTextContent('Not recorded');
    expect(dateRow('Done on').querySelector('time')).toBeNull();
    expect(dateRow('Scheduled for')).toHaveTextContent('Not recorded');
  });

  it('retains an older saved homework classification while explaining that its deadline was not frozen', () => {
    render(<SubmissionTiming kind="homework" record={{ timeliness: 'late', created_at: snapshot.submitted_at, current_due_date: '2026-10-20' }} />);
    expect(dateRow('Due')).toHaveTextContent('Not saved for this submission');
    expect(screen.getByText('Late').parentElement).toHaveTextContent('Recorded timing: Late');
    expect(screen.getByText(/original deadline and schedule were not saved/)).toBeInTheDocument();
  });

  it('keeps an undated one-time chore undated and never assigns an on-time result', () => {
    render(<SubmissionTiming kind="chore" record={{ timing_snapshot: { ...snapshot, schedule: 'one_time', due_on: null, timeliness: null } }} />);
    expect(dateRow('Scheduled for')).toHaveTextContent('No scheduled date');
    expect(screen.queryByText('Timing unknown')).not.toBeInTheDocument();
    expect(screen.queryByText('On time')).not.toBeInTheDocument();
  });

  it('keeps the two household days visible and later approval in details without timing badges', () => {
    render(<SubmissionTiming kind="chore" record={{ timing_snapshot: { ...snapshot, schedule: 'daily' }, status: 'approved', decided_at: '2026-10-20T18:00:00Z' }} />);
    expect(screen.queryByText('On schedule')).not.toBeInTheDocument();
    expect(screen.queryByText('On time')).not.toBeInTheDocument();
    expect(screen.queryByText('Missed')).not.toBeInTheDocument();
    expect(dateRow('Done on').querySelector('time')).toHaveAttribute('datetime', '2026-10-16');
    expect(dateRow('Approved').closest('details')).not.toHaveAttribute('open');
  });

  it('uses the family timezone for old timestamps instead of shifting the visible day to UTC', () => {
    render(<SubmissionTiming kind="chore" timezone="America/Phoenix" record={{
      completed_date: '2026-10-17', current_due_date: null,
      created_at: '2026-10-18T01:35:00Z',
    }} />);
    expect(dateRow('Done on').querySelector('time')).toHaveAttribute('datetime', '2026-10-17');
    expect(dateRow('Marked complete')).toHaveTextContent('MST');
    expect(dateRow('Marked complete')).not.toHaveTextContent('UTC');
    expect(screen.queryByText('No due date')).not.toBeInTheDocument();
  });

  it('keeps changed one-time schedules in details without replacing the saved scheduled date', () => {
    render(<SubmissionTiming kind="chore" record={{
      timing_snapshot: { ...snapshot, schedule: 'one_time' }, current_due_date: '2026-10-20',
    }} />);
    expect(dateRow('Scheduled for').querySelector('time')).toHaveAttribute('datetime', snapshot.due_on);
    expect(screen.getByText('The schedule changed after this submission.')).toBeInTheDocument();
    expect(screen.getByText('Now scheduled for').closest('details')).not.toHaveAttribute('open');
    expect(dateRow('Now scheduled for').querySelector('time')).toHaveAttribute('datetime', '2026-10-20');
  });

  it('prefers the saved timezone and falls back safely when a timezone is invalid', () => {
    const { rerender } = render(<SubmissionTiming kind="chore" timezone="Asia/Tokyo" record={{ timing_snapshot: snapshot }} />);
    expect(dateRow('Marked complete')).toHaveTextContent('Oct 16');
    expect(dateRow('Marked complete')).toHaveTextContent('MST');
    rerender(<SubmissionTiming kind="chore" timezone="invalid" record={{
      timing_snapshot: { ...snapshot, timezone: 'invalid' },
    }} />);
    expect(dateRow('Marked complete')).toHaveTextContent('Oct 16');
    expect(dateRow('Marked complete')).toHaveTextContent('MST');
  });
});
