import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ClockPage from './ClockPage.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildParent, buildUser, buildProject } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(user = buildUser(), handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ClockPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('ClockPage', () => {
  it('renders idle state with project dropdown', async () => {
    renderPage(buildUser(), [
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
      http.get('*/api/projects/', () =>
        HttpResponse.json([buildProject({ id: 1, title: 'Alpha', status: 'active' })]),
      ),
      http.get('*/api/time-entries/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
    expect(screen.getByText(/no entries yet/i)).toBeInTheDocument();
  });

  it('requires a project selection before clocking in', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
      http.get('*/api/projects/', () => HttpResponse.json([])),
      http.get('*/api/time-entries/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText('Clock')).toBeInTheDocument());
    const btn = screen.getAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-play'));
    await user.click(btn);
    await waitFor(() =>
      expect(screen.getAllByText(/select a venture/i).length).toBeGreaterThanOrEqual(2),
    );
  });

  it('clocks out of an active session and appends a note', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/clock/', () =>
        HttpResponse.json({
          status: 'active',
          project_title: 'Ongoing',
          clock_in: new Date(Date.now() - 5000).toISOString(),
        }),
      ),
      http.get('*/api/projects/', () => HttpResponse.json([])),
      http.get('*/api/time-entries/', () => HttpResponse.json([])),
      http.post('*/api/clock/', () => HttpResponse.json({ ok: true })),
    ]);
    await waitFor(() => expect(screen.getByText(/now inking/i)).toBeInTheDocument());
    await user.type(screen.getByPlaceholderText(/scribble what you did/i), 'Great stuff');
    const stop = screen.getAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-square'));
    await user.click(stop);
    // Just asserting no throw
  });

  it('renders entries list and voids an entry (parent only)', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
      http.get('*/api/projects/', () => HttpResponse.json([])),
      http.get('*/api/time-entries/', () =>
        HttpResponse.json([
          { id: 9, project_title: 'Past', clock_in: '2026-04-10T12:00:00Z', duration_minutes: 90, status: 'completed', notes: 'did things' },
          { id: 10, project_title: 'Voided', clock_in: '2026-04-11T12:00:00Z', duration_minutes: 30, status: 'voided' },
        ]),
      ),
      http.post(/\/api\/time-entries\/9\/void\/$/, () => HttpResponse.json({})),
    ]);
    await waitFor(() => expect(screen.getByText('Past')).toBeInTheDocument());
    // Click the void (Ban) icon button
    const voidBtn = screen.getByRole('button', { name: /void entry/i });
    await user.click(voidBtn);
    // Confirm dialog renders
    await user.click(await screen.findByRole('button', { name: 'Void' }));
  });

  it('cancels the void confirmation', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
      http.get('*/api/projects/', () => HttpResponse.json([])),
      http.get('*/api/time-entries/', () =>
        HttpResponse.json([
          { id: 1, project_title: 'P', clock_in: '2026-04-10T12:00:00Z', duration_minutes: 60, status: 'completed' },
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('P')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /void entry/i }));
    await user.click(await screen.findByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('button', { name: 'Void' })).toBeNull();
  });

  it('clocking in posts {action:"in", project_id:N} to /clock/', async () => {
    const user = userEvent.setup();
    const clock = spyHandler('post', '*/api/clock/', { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
      http.get('*/api/projects/', () =>
        HttpResponse.json([buildProject({ id: 7, title: 'Alpha', status: 'active' })]),
      ),
      http.get('*/api/time-entries/', () => HttpResponse.json([])),
      clock.handler,
    ]);
    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
    await user.selectOptions(screen.getByRole('combobox'), '7');
    const play = screen.getAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-play'));
    await user.click(play);

    await waitFor(() => expect(clock.calls).toHaveLength(1));
    expect(clock.calls[0].body).toEqual({ action: 'in', project_id: 7 });
  });

  it('clocking out posts {action:"out", notes:"…"} to /clock/', async () => {
    const user = userEvent.setup();
    const clock = spyHandler('post', '*/api/clock/', { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/clock/', () =>
        HttpResponse.json({
          status: 'active',
          project_title: 'Ongoing',
          clock_in: new Date(Date.now() - 5000).toISOString(),
        }),
      ),
      http.get('*/api/projects/', () => HttpResponse.json([])),
      http.get('*/api/time-entries/', () => HttpResponse.json([])),
      clock.handler,
    ]);
    await waitFor(() => expect(screen.getByText(/now inking/i)).toBeInTheDocument());
    await user.type(screen.getByPlaceholderText(/scribble what you did/i), 'Great stuff');
    const stop = screen.getAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-square'));
    await user.click(stop);

    await waitFor(() => expect(clock.calls).toHaveLength(1));
    expect(clock.calls[0].body).toEqual({ action: 'out', notes: 'Great stuff' });
  });

  it('shows a confirm dialog before clocking out of a long session (>60s)', async () => {
    const user = userEvent.setup();
    const clock = spyHandler('post', '*/api/clock/', { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/clock/', () =>
        HttpResponse.json({
          status: 'active',
          project_title: 'Long Session',
          // 30 minutes ago — well past the misclick-recovery threshold.
          clock_in: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
        }),
      ),
      http.get('*/api/projects/', () => HttpResponse.json([])),
      http.get('*/api/time-entries/', () => HttpResponse.json([])),
      clock.handler,
    ]);
    await waitFor(() => expect(screen.getByText(/now inking/i)).toBeInTheDocument());
    const stop = screen.getAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-square'));
    await user.click(stop);
    // The clock-out should NOT have fired yet — the confirm dialog gates it.
    expect(clock.calls).toHaveLength(0);
    // Confirming closes the entry.
    await user.click(await screen.findByRole('button', { name: /close entry/i }));
    await waitFor(() => expect(clock.calls).toHaveLength(1));
    expect(clock.calls[0].body).toEqual({ action: 'out', notes: '' });
  });

  it('cancels the clock-out confirm without firing the request', async () => {
    const user = userEvent.setup();
    const clock = spyHandler('post', '*/api/clock/', { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/clock/', () =>
        HttpResponse.json({
          status: 'active',
          project_title: 'Long Session',
          clock_in: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
        }),
      ),
      http.get('*/api/projects/', () => HttpResponse.json([])),
      http.get('*/api/time-entries/', () => HttpResponse.json([])),
      clock.handler,
    ]);
    await waitFor(() => expect(screen.getByText(/now inking/i)).toBeInTheDocument());
    const stop = screen.getAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-square'));
    await user.click(stop);
    await user.click(await screen.findByRole('button', { name: /cancel/i }));
    expect(clock.calls).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /close entry/i })).toBeNull();
  });

  it('does not paint the idle Play seal while the clock status is still loading', async () => {
    // A kid who IS clocked in used to see (and could tap) the idle
    // 00:00:00 + Play seal during the status round-trip.
    let releaseStatus;
    const gate = new Promise((r) => { releaseStatus = r; });
    renderPage(buildUser(), [
      http.get('*/api/clock/', async () => {
        await gate;
        return HttpResponse.json({
          status: 'active',
          project_title: 'Ongoing',
          clock_in: new Date(Date.now() - 5000).toISOString(),
        });
      }),
      http.get('*/api/projects/', () => HttpResponse.json([])),
      http.get('*/api/time-entries/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText('Clock')).toBeInTheDocument());
    expect(screen.queryByText('00:00:00')).toBeNull();
    expect(
      screen.queryAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-play')),
    ).toBeUndefined();

    releaseStatus();
    await waitFor(() => expect(screen.getByText(/now inking/i)).toBeInTheDocument());
  });

  it('holds the entries empty state until the entries fetch resolves', async () => {
    let releaseEntries;
    const gate = new Promise((r) => { releaseEntries = r; });
    renderPage(buildUser(), [
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
      http.get('*/api/projects/', () => HttpResponse.json([])),
      http.get('*/api/time-entries/', async () => {
        await gate;
        return HttpResponse.json([
          { id: 4, project_title: 'Past', clock_in: '2026-04-10T12:00:00Z', duration_minutes: 60, status: 'completed' },
        ]);
      }),
    ]);
    await waitFor(() => expect(screen.getByText('Clock')).toBeInTheDocument());
    expect(screen.queryByText(/no entries yet/i)).toBeNull();

    releaseEntries();
    await waitFor(() => expect(screen.getByText('Past')).toBeInTheDocument());
    expect(screen.queryByText(/no entries yet/i)).toBeNull();
  });

  it('double-tapping the Play seal only posts one clock-in', async () => {
    const user = userEvent.setup();
    let releaseStatusReload;
    const reloadGate = new Promise((r) => { releaseStatusReload = r; });
    let statusCalls = 0;
    const clock = spyHandler('post', '*/api/clock/', { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/clock/', async () => {
        statusCalls += 1;
        // Hold the post-clock-in status refetch so the seal stays busy.
        if (statusCalls > 1) await reloadGate;
        return HttpResponse.json({ status: 'idle' });
      }),
      http.get('*/api/projects/', () =>
        HttpResponse.json([buildProject({ id: 7, title: 'Alpha', status: 'active' })]),
      ),
      http.get('*/api/time-entries/', () => HttpResponse.json([])),
      clock.handler,
    ]);
    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
    await user.selectOptions(screen.getByRole('combobox'), '7');

    const play = () =>
      screen.getAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-play'));
    await user.click(play());
    await waitFor(() => expect(play()).toBeDisabled());
    await user.click(play());

    releaseStatusReload();
    await waitFor(() => expect(play()).toBeEnabled());
    expect(clock.calls).toHaveLength(1);
  });

  it('surfaces clock-in server error', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
      http.get('*/api/projects/', () =>
        HttpResponse.json([buildProject({ id: 1, title: 'Alpha', status: 'active' })]),
      ),
      http.get('*/api/time-entries/', () => HttpResponse.json([])),
      http.post('*/api/clock/', () =>
        HttpResponse.json({ error: 'quiet hours' }, { status: 400 }),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
    await user.selectOptions(screen.getByRole('combobox'), '1');
    const play = screen.getAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-play'));
    await user.click(play);
    expect(await screen.findByText(/quiet hours/i)).toBeInTheDocument();
  });
});
