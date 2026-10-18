import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server } from '../test/server';
import { buildParent } from '../test/factories';
import { AuthProvider } from '../hooks/useApi';
import { getChoreCompletions, getHomeworkDetail } from './index';
import SubmissionTiming from '../components/SubmissionTiming';
import ReviewedWorkHistory from '../components/ReviewedWorkHistory';
import AssignmentCard from '../pages/Homework/AssignmentCard';
import weekly from '../../../contracts/api/fixtures/completion-timing-weekly-pending.json';
import chores from '../../../contracts/api/fixtures/completion-timing-chore-reviewed.json';
import homework from '../../../contracts/api/fixtures/completion-timing-homework-reviewed.json';
import assignment from '../../../contracts/api/fixtures/completion-timing-homework-assignment.json';

describe('real submission timing response contracts in React', () => {
  it('shows the saved scheduled day and actual done day without rewriting API evidence', async () => {
    server.use(http.get('*/api/chore-completions/', () => HttpResponse.json([weekly])));
    const rows = await getChoreCompletions('pending');
    const { container } = render(<SubmissionTiming record={rows[0]} kind="chore" />);
    expect(screen.getAllByText('Scheduled for')).toHaveLength(1);
    expect(screen.getAllByText('Done on')).toHaveLength(1);
    expect(container.querySelector('time[datetime="2026-10-19"]')).not.toBeInTheDocument();
    expect(container.querySelectorAll(`time[datetime="${weekly.timing_snapshot.due_on}"]`)).toHaveLength(1);
    const doneDay = container.querySelector(`time[datetime="${weekly.timing_snapshot.submitted_on}"]`);
    expect(doneDay).toBeVisible();
    expect(doneDay).toHaveTextContent(/^10\/23\/2026$/);
    expect(screen.queryByText('On time')).not.toBeInTheDocument();
    expect(screen.queryByText(/^(Missed|On schedule|Timing unknown)$/)).not.toBeInTheDocument();
    expect(rows[0].timing_snapshot.timeliness).toBe('on_time');
    expect(rows[0].timing_snapshot.submitted_at).toBe(weekly.timing_snapshot.submitted_at);
    expect(screen.queryByText('Due')).not.toBeInTheDocument();
    expect(screen.queryByText('Scheduled week')).not.toBeInTheDocument();
    expect(screen.queryByText('Current due')).not.toBeInTheDocument();
  });

  it('shows reviewed chore dates while keeping later approval metadata collapsed', async () => {
    const user = userEvent.setup();
    let historyReads = 0;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/chore-completions/', () => {
        historyReads += 1;
        return HttpResponse.json(chores);
      }),
    );
    const { container } = render(<AuthProvider><ReviewedWorkHistory kind="chore" childId={7} /></AuthProvider>);
    await user.click(await screen.findByText('Reviewed chores'));
    expect(await screen.findByText('Abby · Tidy the desk')).toBeInTheDocument();
    expect(screen.queryByText('On time')).not.toBeInTheDocument();
    expect(screen.queryByText(/^(Missed|On schedule|Timing unknown)$/)).not.toBeInTheDocument();
    expect(screen.getAllByText('Scheduled for')).toHaveLength(1);
    expect(container.querySelectorAll(`time[datetime="${chores.results[0].timing_snapshot.due_on}"]`)).toHaveLength(1);
    expect(screen.queryByText('Due')).not.toBeInTheDocument();
    expect(screen.queryByText('Current due')).not.toBeInTheDocument();
    expect(screen.getAllByText('Done on')).toHaveLength(1);
    expect(container.querySelector(`time[datetime="${weekly.timing_snapshot.submitted_on}"]`)).toBeVisible();
    const details = screen.getByText('Completion details').closest('details');
    expect(details).not.toHaveAttribute('open');
    const approvalTime = container.querySelector(`time[datetime="${chores.results[0].decided_at}"]`);
    expect(details).toContainElement(approvalTime);
    expect(approvalTime).not.toBeVisible();
    await user.click(screen.getByText('Completion details'));
    await waitFor(() => {
      expect(screen.getByText('Completion details').closest('details')).toHaveAttribute('open');
      expect(container.querySelector(`time[datetime="${chores.results[0].decided_at}"]`)).toBeVisible();
    });
    await user.click(screen.getByText('Completion details'));
    await waitFor(() => {
      expect(screen.getByText('Completion details').closest('details')).not.toHaveAttribute('open');
      expect(screen.getByText('Reviewed chores').closest('details')).toHaveAttribute('open');
      expect(screen.getByText('Abby · Tidy the desk')).toBeVisible();
      expect(container.querySelector(`time[datetime="${chores.results[0].decided_at}"]`)).not.toBeVisible();
    });
    expect(historyReads).toBe(1);
  });

  it('shows the original homework deadline, later edit and later approval as distinct dates', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/homework-submissions/', () => HttpResponse.json(homework)),
      http.get('*/api/homework/31/', () => HttpResponse.json(assignment)),
    );
    const { container, unmount } = render(<AuthProvider><ReviewedWorkHistory kind="homework" childId={7} /></AuthProvider>);
    await user.click(await screen.findByText('Reviewed homework'));
    expect(await screen.findByText('Abby · Reading worksheet')).toBeInTheDocument();
    expect(screen.getByText('Late')).toBeInTheDocument();
    expect(container.querySelector('time[datetime="2026-10-22"]')).toBeInTheDocument();
    expect(container.querySelector(`time[datetime="${homework.results[0].decided_at}"]`)).toBeInTheDocument();
    unmount();
    const saved = await getHomeworkDetail(31);
    const child = render(<MemoryRouter><AssignmentCard assignment={saved} /></MemoryRouter>);
    expect(screen.getByText('Submitted')).toBeInTheDocument();
    expect(child.container.querySelector('time[datetime="2026-10-22"]')).toBeInTheDocument();
    expect(screen.getByText('Late')).toBeInTheDocument();
    expect(screen.queryByText(/-50%|\+25%/)).not.toBeInTheDocument();
  });
});
