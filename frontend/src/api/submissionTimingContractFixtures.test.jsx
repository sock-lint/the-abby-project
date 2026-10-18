import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen } from '@testing-library/react';
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
  it('keeps the weekly period separate from the actual Friday completion timestamp', async () => {
    server.use(http.get('*/api/chore-completions/', () => HttpResponse.json([weekly])));
    const rows = await getChoreCompletions('pending');
    const { container } = render(<SubmissionTiming record={rows[0]} kind="chore" />);
    expect(screen.getByText('Scheduled week')).toBeInTheDocument();
    expect(screen.getByText('Marked complete')).toBeInTheDocument();
    expect(container.querySelector('time[datetime="2026-10-19"]')).toBeInTheDocument();
    expect(container.querySelector('time[datetime="2026-10-25"]')).toBeInTheDocument();
    expect(container.querySelector(`time[datetime="${weekly.timing_snapshot.submitted_at}"]`)).toHaveTextContent(/Oct 23, 2026/);
    expect(screen.getByText('On time')).toBeInTheDocument();
    expect(screen.queryByText('Current due')).not.toBeInTheDocument();
  });

  it('reads reviewed chores through the real history client without changing saved timeliness', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/chore-completions/', () => HttpResponse.json(chores)),
    );
    const { container } = render(<AuthProvider><ReviewedWorkHistory kind="chore" childId={7} /></AuthProvider>);
    await user.click(await screen.findByText('Reviewed chores'));
    expect(await screen.findByText('Abby · Tidy the desk')).toBeInTheDocument();
    expect(screen.getByText('On time')).toBeInTheDocument();
    expect(container.querySelector(`time[datetime="${chores.results[0].decided_at}"]`)).toBeInTheDocument();
    expect(container.querySelector(`time[datetime="${weekly.timing_snapshot.submitted_at}"]`)).toHaveTextContent(/Oct 23, 2026/);
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
