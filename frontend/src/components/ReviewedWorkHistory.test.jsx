import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, renderWithProviders, screen, waitFor } from '../test/render';
import { server } from '../test/server';
import { buildParent } from '../test/factories';
import { useAuth } from '../hooks/useApi';
import { approveChoreCompletion, rejectHomeworkSubmission } from '../api';
import { getToken } from '../api/client';
import { PARENT_REVIEW_CHANGED } from '../api/parentReviewRefresh';
import { spyHandler } from '../test/spy';
import ReviewedWorkHistory from './ReviewedWorkHistory';

const parent = buildParent({ family: { id: 1 } });
const row = (id, overrides = {}) => ({
  id, user: 7, user_name: 'Abby', assignment_title: `Assignment ${id}`,
  status: 'approved', created_at: '2026-10-17T18:00:00Z', decided_at: '2026-10-19T18:00:00Z', proofs: [],
  ...overrides,
});
function authenticate() {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(parent)));
}

describe('Reviewed work history', () => {
  it.each([
    ['chore', 'Reviewed chores', '/api/chore-completions/', 'approve', approveChoreCompletion, null],
    ['homework', 'Reviewed homework', '/api/homework-submissions/', 'reject', rejectHomeworkSubmission, { notes: '' }],
  ])('refreshes open %s history after a confirmed decision', async (kind, title, endpoint, decision, save, body) => {
    authenticate();
    let decided = false;
    const requests = [];
    const write = spyHandler('post', new RegExp(`${endpoint}9/${decision}/$`), () => {
      decided = true;
      return { id: 9, status: decision === 'approve' ? 'approved' : 'rejected' };
    });
    server.use(write.handler, http.get(`*${endpoint}`, ({ request }) => {
      requests.push(new URL(request.url));
      return HttpResponse.json(decided ? [row(9, {
        chore_title: kind === 'chore' ? 'Newly reviewed work' : undefined,
        assignment_title: 'Newly reviewed work', status: decision === 'approve' ? 'approved' : 'rejected',
      })] : []);
    }));
    const { user } = renderWithProviders(<><button onClick={() => { void save(9); }}>Save decision</button><ReviewedWorkHistory kind={kind} childId={7} /></>);
    await user.click(await screen.findByText(title));
    await screen.findByText('No reviewed work yet.');
    await user.click(screen.getByRole('button', { name: 'Save decision' }));
    await waitFor(() => expect(write.calls).toHaveLength(1));
    expect(write.calls[0].url).toContain(`${endpoint}9/${decision}/`);
    expect(write.calls[0].body).toEqual(body);
    await screen.findByText('Abby · Newly reviewed work');
    expect(requests).toHaveLength(2);
    requests.forEach((url) => {
      expect(url.searchParams.get('page')).toBe('1');
      expect(url.searchParams.get('user_id')).toBe('7');
    });
  });

  it('coalesces review changes and restarts an open paginated history from page one', async () => {
    authenticate();
    let changed = false;
    const pages = [];
    server.use(http.get('*/api/homework-submissions/', ({ request }) => {
      const page = new URL(request.url).searchParams.get('page');
      pages.push(page);
      return HttpResponse.json(changed ? { results: [row(99)], next: null }
        : page === '1' ? { results: [row(1)], next: '/api/homework-submissions/?page=2' }
          : { results: [row(2)], next: null });
    }));
    const { user } = renderWithProviders(<ReviewedWorkHistory kind="homework" childId={7} />);
    await user.click(await screen.findByText('Reviewed homework'));
    await screen.findByText('Abby · Assignment 1');
    await user.click(screen.getByRole('button', { name: 'Load more reviewed work' }));
    await screen.findByText('Abby · Assignment 2');
    changed = true;
    act(() => {
      for (let index = 0; index < 3; index += 1) window.dispatchEvent(new CustomEvent(PARENT_REVIEW_CHANGED, { detail: { token: getToken() } }));
    });
    await screen.findByText('Abby · Assignment 99');
    expect(pages).toEqual(['1', '2', '1']);
    expect(screen.queryByText('Abby · Assignment 2')).not.toBeInTheDocument();
  });

  it('ignores former-account events and does not refresh while the disclosure is closed', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      authenticate();
      const requests = [];
      server.use(http.get('*/api/homework-submissions/', ({ request }) => {
        requests.push(request.url);
        return HttpResponse.json([row(1)]);
      }));
      const { user } = renderWithProviders(<ReviewedWorkHistory kind="homework" childId={7} />);
      const summary = await screen.findByText('Reviewed homework');
      await user.click(summary);
      await screen.findByText('Abby · Assignment 1');
      act(() => window.dispatchEvent(new CustomEvent(PARENT_REVIEW_CHANGED, { detail: { token: 'former-account-token' } })));
      await act(async () => { await vi.advanceTimersByTimeAsync(100); });
      expect(requests).toHaveLength(1);
      await user.click(summary);
      await waitFor(() => expect(summary.closest('details')).not.toHaveAttribute('open'));
      act(() => window.dispatchEvent(new CustomEvent(PARENT_REVIEW_CHANGED, { detail: { token: getToken() } })));
      await act(async () => { await vi.advanceTimersByTimeAsync(100); });
      expect(requests).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not offer a family-wide read when no verified child is selected', async () => {
    authenticate();
    const requests = [];
    server.use(http.get('*/api/homework-submissions/', ({ request }) => { requests.push(request.url); return HttpResponse.json([]); }));
    function Workspace() {
      const { user } = useAuth();
      return <>{user && <p>Parent ready</p>}<ReviewedWorkHistory kind="homework" childId={null} /></>;
    }
    renderWithProviders(<Workspace />);
    await screen.findByText('Parent ready');
    expect(screen.queryByText('Reviewed homework')).not.toBeInTheDocument();
    expect(requests).toHaveLength(0);
  });

  it('keeps earlier rows through a page failure and retries the same known endpoint with the verified child', async () => {
    authenticate();
    const requests = [];
    let failed = false;
    server.use(http.get('*/api/homework-submissions/', ({ request }) => {
      const url = new URL(request.url);
      requests.push(url);
      if (url.searchParams.get('page') === '1') return HttpResponse.json({
        count: 21, next: 'https://untrusted.example/api/homework-submissions/?page=2&user_id=666',
        results: Array.from({ length: 20 }, (_, index) => row(index + 1)),
      });
      if (!failed) { failed = true; return HttpResponse.json({ error: 'History page unavailable.' }, { status: 500 }); }
      return HttpResponse.json({ count: 21, next: null, results: [row(21), row(22, { user: 8, user_name: 'Sibling' }), row(23, { status: 'pending' })] });
    }));
    const { user } = renderWithProviders(<ReviewedWorkHistory kind="homework" childId={7} />);
    await user.click(await screen.findByText('Reviewed homework'));
    await screen.findByText('Abby · Assignment 20');
    await user.click(screen.getByRole('button', { name: 'Load more reviewed work' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('History page unavailable.');
    expect(screen.getByText('Abby · Assignment 1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry reviewed work' }));
    await screen.findByText('Abby · Assignment 21');
    expect(requests).toHaveLength(3);
    expect(requests.map((url) => url.searchParams.get('page'))).toEqual(['1', '2', '2']);
    requests.forEach((url) => {
      expect(url.pathname).toBe('/api/homework-submissions/');
      expect(url.hostname).not.toBe('untrusted.example');
      expect(url.searchParams.get('status')).toBe('reviewed');
      expect(url.searchParams.get('user_id')).toBe('7');
    });
    expect(screen.getAllByText(/^Abby · Assignment /)).toHaveLength(21);
    expect(screen.queryByText('Sibling · Assignment 22')).not.toBeInTheDocument();
    expect(screen.queryByText('Abby · Assignment 23')).not.toBeInTheDocument();
  });

  it('ignores a delayed history response from a previously selected child', async () => {
    authenticate();
    let releaseOld;
    const oldReady = new Promise((resolve) => { releaseOld = resolve; });
    let oldStarted = false;
    let oldReturned = false;
    server.use(http.get('*/api/homework-submissions/', async ({ request }) => {
      if (new URL(request.url).searchParams.get('user_id') === '7') {
        oldStarted = true;
        await oldReady;
        oldReturned = true;
        return HttpResponse.json([row(1)]);
      }
      return HttpResponse.json([row(2, { user: 8, user_name: 'Beck' })]);
    }));
    function Workspace() {
      const [child, setChild] = useState(7);
      return <><button onClick={() => setChild(8)}>View Beck</button><ReviewedWorkHistory kind="homework" childId={child} /></>;
    }
    const { user } = renderWithProviders(<Workspace />);
    await user.click(await screen.findByText('Reviewed homework'));
    await waitFor(() => expect(oldStarted).toBe(true));
    await user.click(screen.getByRole('button', { name: 'View Beck' }));
    await user.click(screen.getByText('Reviewed homework'));
    await screen.findByText('Beck · Assignment 2');
    await act(async () => { releaseOld(); });
    await waitFor(() => expect(oldReturned).toBe(true));
    expect(screen.queryByText('Abby · Assignment 1')).not.toBeInTheDocument();
    expect(screen.getByText('Beck · Assignment 2')).toBeInTheDocument();
  });

  it('clears reviewed notes and reopens history under a replacement account credential', async () => {
    authenticate();
    const requests = [];
    server.use(http.get('*/api/homework-submissions/', ({ request }) => {
      requests.push(request.headers.get('Authorization'));
      const changed = request.headers.get('Authorization') === 'Token replacement-token';
      return HttpResponse.json([row(changed ? 2 : 1, { notes: changed ? 'New account note' : 'Earlier account note' })]);
    }));
    function Workspace() {
      const { setUser } = useAuth();
      return <><button onClick={() => {
        localStorage.setItem('abby_auth_token', 'replacement-token');
        setUser(buildParent({ id: 100, family: { id: 2 } }));
      }}>Switch account</button><ReviewedWorkHistory kind="homework" childId={7} /></>;
    }
    const { user } = renderWithProviders(<Workspace />);
    await user.click(await screen.findByText('Reviewed homework'));
    await screen.findByText('Earlier account note');
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    expect(screen.queryByText('Earlier account note')).not.toBeInTheDocument();
    await user.click(screen.getByText('Reviewed homework'));
    await screen.findByText('New account note');
    expect(requests).toEqual(['Token test-session', 'Token replacement-token']);
  });
});
