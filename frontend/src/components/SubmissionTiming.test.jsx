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

  it('shows a weekly schedule and its last day separately from the actual marked-complete timestamp', () => {
    render(<SubmissionTiming kind="chore" record={{ timing_snapshot: {
      ...snapshot, schedule: 'weekly', period_start: '2026-10-12', period_end: '2026-10-18', due_on: '2026-10-18',
    } }} />);
    expect(dateRow('Scheduled week').querySelectorAll('time')[0]).toHaveAttribute('datetime', '2026-10-12');
    expect(dateRow('Scheduled week').querySelectorAll('time')[1]).toHaveAttribute('datetime', '2026-10-18');
    expect(dateRow('Due').querySelector('time')).toHaveAttribute('datetime', '2026-10-18');
    expect(dateRow('Marked complete').querySelector('time')).toHaveAttribute('datetime', snapshot.submitted_at);
  });

  it('labels older chore timing unknown without treating the period key as its completion timestamp', () => {
    render(<SubmissionTiming kind="chore" record={{ completed_date: '2026-10-12', created_at: '2026-10-16T18:30:00Z' }} />);
    expect(dateRow('Recorded period date').querySelector('time')).toHaveAttribute('datetime', '2026-10-12');
    expect(dateRow('Marked complete').querySelector('time')).toHaveAttribute('datetime', '2026-10-16T18:30:00Z');
    expect(screen.getByText('Timing unknown')).toBeInTheDocument();
    expect(screen.queryByText('On time')).not.toBeInTheDocument();
  });

  it('does not invent a submitted timestamp when only the older period date is available', () => {
    render(<SubmissionTiming kind="chore" record={{ completed_date: '2026-10-12' }} />);
    expect(dateRow('Marked complete')).toHaveTextContent('Not recorded');
    expect(dateRow('Marked complete').querySelector('time')).toBeNull();
    expect(screen.getByText('Timing unknown')).toBeInTheDocument();
  });

  it('retains an older saved homework classification while explaining that its deadline was not frozen', () => {
    render(<SubmissionTiming kind="homework" record={{ timeliness: 'late', created_at: snapshot.submitted_at, current_due_date: '2026-10-20' }} />);
    expect(dateRow('Due')).toHaveTextContent('Not saved for this submission');
    expect(screen.getByText('Late').parentElement).toHaveTextContent('Recorded timing: Late');
    expect(screen.getByText(/original deadline and schedule were not saved/)).toBeInTheDocument();
  });

  it('keeps an undated one-time chore undated and never assigns an on-time result', () => {
    render(<SubmissionTiming kind="chore" record={{ timing_snapshot: { ...snapshot, schedule: 'one_time', due_on: null, timeliness: null } }} />);
    expect(dateRow('Due')).toHaveTextContent('No due date');
    expect(screen.queryByText('Timing unknown')).not.toBeInTheDocument();
    expect(screen.queryByText('On time')).not.toBeInTheDocument();
  });
});
