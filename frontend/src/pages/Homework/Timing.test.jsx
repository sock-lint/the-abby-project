import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, renderWithProviders, screen, waitFor, within } from '../../test/render';
import Homework from './index';
import AssignmentCard from './AssignmentCard';
import { server } from '../../test/server';
import { buildParent } from '../../test/factories';
import { spyHandler } from '../../test/spy';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const timing = {
  version: 1, timezone: 'America/New_York', schedule: 'homework',
  submitted_at: '2026-10-17T22:00:00+00:00', submitted_on: '2026-10-17', due_on: '2026-10-17',
  period_start: null, period_end: null, timeliness: 'on_time',
};
const submission = {
  id: 9, assignment: 42, assignment_title: 'Reading log', user: 7, user_name: 'Abby', status: 'pending',
  proofs: [], notes: '', created_at: timing.submitted_at, timeliness: 'on_time',
  timing_snapshot: timing, current_due_date: '2026-10-20',
};

describe('Homework timing', () => {
  it('shows the due and submitted date on a parent pending review', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', () => HttpResponse.json([{ id: 7, username: 'abby', display_name: 'Abby' }])),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ assignments: [], pending_submissions: [submission] })),
    );
    renderWithProviders(<Homework />);
    const title = await screen.findByText('Reading log');
    const review = within(title.closest('[data-parchment-card]') || title.closest('.space-y-3'));
    expect(await review.findByText('Due', { exact: true })).toBeInTheDocument();
    expect(review.getByText('Submitted', { exact: true })).toBeInTheDocument();
  });

  it.each([false, true])('retains one current deadline beside saved timing on an approved assignment (parent: %s)', (canManage) => {
    renderWithProviders(<AssignmentCard assignment={{
      id: 42, title: 'Reading log', subject: 'reading', due_date: '2026-10-20', effort_level: 3,
      submission_status: { ...submission, status: 'approved', decided_at: '2026-10-19T18:00:00Z' },
    }} canManage={canManage} />, { withAuth: false });
    expect(screen.getByText('Due', { exact: true })).toBeInTheDocument();
    expect(screen.getByText('Submitted', { exact: true })).toBeInTheDocument();
    expect(screen.getAllByText(/^current due/i)).toHaveLength(1);
    expect(screen.getByText('Due', { exact: true }).parentElement.querySelector('time')).toHaveAttribute('datetime', '2026-10-17');
    expect(screen.getByText('Current due', { exact: true }).parentElement.querySelector('time')).toHaveAttribute('datetime', '2026-10-20');
    expect(document.querySelector('time[datetime="2026-10-19T18:00:00Z"]')).toBeInTheDocument();
  });

  it('reads reviewed homework for the selected child with its original deadline and separate approval date', async () => {
    let finishRoster;
    let rosterStarted = false;
    const roster = new Promise((resolve) => { finishRoster = resolve; });
    const history = spyHandler('get', '*/api/homework-submissions/', {
      count: 1, next: null, results: [{ ...submission, status: 'approved', decided_at: '2026-10-19T18:00:00Z' }],
    });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/children/', async () => { rosterStarted = true; await roster; return HttpResponse.json([{ id: 7, username: 'abby', display_name: 'Abby' }]); }),
      http.get('*/api/homework/dashboard/', () => HttpResponse.json({ assignments: [], pending_submissions: [] })),
      history.handler,
    );
    const { user } = renderWithProviders(<Homework />, { route: '/quests?tab=study&child=999' });
    await waitFor(() => expect(rosterStarted).toBe(true));
    expect(screen.queryByText('Reviewed homework')).not.toBeInTheDocument();
    expect(history.calls).toHaveLength(0);
    await act(async () => { finishRoster(); });
    await user.click(await screen.findByText('Reviewed homework'));
    await waitFor(() => expect(history.calls).toHaveLength(1));
    const query = new URL(history.calls[0].url).searchParams;
    expect(query.get('status')).toBe('reviewed');
    expect(query.get('user_id')).toBe('7');
    expect(query.get('page')).toBe('1');
    expect(await screen.findByText('Abby · Reading log')).toBeInTheDocument();
    const originalDue = document.querySelector('time[datetime="2026-10-17"]');
    expect(originalDue).toBeInTheDocument();
    expect(document.querySelector('time[datetime="2026-10-19T18:00:00Z"]')).toBeInTheDocument();
    expect(screen.getByText('On time')).toBeInTheDocument();
  });
});
