import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import ClockFab from './ClockFab.jsx';
import { server } from '../../test/server.js';
import { buildProject } from '../../test/factories.js';

function renderFab() {
  return render(
    <MemoryRouter>
      <ClockFab />
    </MemoryRouter>,
  );
}

describe('ClockFab', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders the "Clock" FAB label when not clocked in', async () => {
    server.use(
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
    );
    renderFab();
    await waitFor(() => expect(screen.getByText('Clock')).toBeInTheDocument());
  });

  it('renders an elapsed label when clocked in', async () => {
    server.use(
      http.get('*/api/clock/', () =>
        HttpResponse.json({
          status: 'active',
          clock_in: new Date(Date.now() - 90 * 1000).toISOString(),
          project_title: 'Bird Feeder',
        }),
      ),
    );
    renderFab();
    // Should show an MM:SS (two-digit minute elapsed).
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /clock out/i })).toBeInTheDocument(),
    );
  });

  it('opens the modal, selects a project, and clocks in', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
      http.get('*/api/projects/', () =>
        HttpResponse.json([
          buildProject({ id: 11, title: 'Alpha', status: 'active' }),
        ]),
      ),
      http.post('*/api/clock/', () => HttpResponse.json({ ok: true })),
    );
    renderFab();
    await waitFor(() => expect(screen.getByText('Clock')).toBeInTheDocument());
    // The FAB and the modal submit button both match "Clock In". Take the
    // first (FAB) to open the modal, then the last (submit) to commit.
    const fab = screen.getAllByRole('button', { name: /clock in/i })[0];
    await user.click(fab);
    const select = await screen.findByLabelText(/which venture/i);
    await user.selectOptions(select, '11');
    const submits = screen.getAllByRole('button', { name: /clock in/i });
    await user.click(submits[submits.length - 1]);
    await waitFor(() => expect(screen.queryByLabelText(/which venture/i)).toBeNull());
  });

  it('errors when clocking in without a project', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
      http.get('*/api/projects/', () => HttpResponse.json([])),
    );
    renderFab();
    await waitFor(() => expect(screen.getByText('Clock')).toBeInTheDocument());
    const fab = screen.getAllByRole('button', { name: /clock in/i })[0];
    await user.click(fab);
    const submits = screen.getAllByRole('button', { name: /clock in/i });
    await user.click(submits[submits.length - 1]);
    expect(await screen.findByText(/select a venture/i)).toBeInTheDocument();
  });

  it('clocks out from an active session', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/clock/', () =>
        HttpResponse.json({
          status: 'active',
          clock_in: new Date(Date.now() - 1000).toISOString(),
          project_title: 'Ongoing',
        }),
      ),
      http.post('*/api/clock/', () => HttpResponse.json({ ok: true })),
    );
    renderFab();
    await waitFor(() => expect(screen.getAllByRole('button', { name: /clock out/i })[0]).toBeInTheDocument());
    const fab = screen.getAllByRole('button', { name: /clock out/i })[0];
    await user.click(fab);
    const submits = await screen.findAllByRole('button', { name: /clock out/i });
    await user.click(submits[submits.length - 1]);
    await waitFor(() => expect(screen.queryByText('Ongoing')).toBeNull());
  });

  it('surfaces clock-in errors', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
      http.get('*/api/projects/', () =>
        HttpResponse.json([buildProject({ id: 11, title: 'Alpha', status: 'active' })]),
      ),
      http.post('*/api/clock/', () =>
        HttpResponse.json({ error: 'quiet hours' }, { status: 400 }),
      ),
    );
    renderFab();
    await waitFor(() => expect(screen.getByText('Clock')).toBeInTheDocument());
    const fab = screen.getAllByRole('button', { name: /clock in/i })[0];
    await user.click(fab);
    const select = await screen.findByLabelText(/which venture/i);
    await user.selectOptions(select, '11');
    const submits = screen.getAllByRole('button', { name: /clock in/i });
    await user.click(submits[submits.length - 1]);
    expect(await screen.findByText(/quiet hours/i)).toBeInTheDocument();
  });

  it('surfaces clock-out errors', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/clock/', () =>
        HttpResponse.json({
          status: 'active',
          clock_in: new Date(Date.now() - 1000).toISOString(),
          project_title: 'Ongoing',
        }),
      ),
      http.post('*/api/clock/', () =>
        HttpResponse.json({ error: 'no active' }, { status: 400 }),
      ),
    );
    renderFab();
    await waitFor(() => expect(screen.getAllByRole('button', { name: /clock out/i })[0]).toBeInTheDocument());
    const fab = screen.getAllByRole('button', { name: /clock out/i })[0];
    await user.click(fab);
    const submits = await screen.findAllByRole('button', { name: /clock out/i });
    await user.click(submits[submits.length - 1]);
    expect(await screen.findByText(/no active/i)).toBeInTheDocument();
  });

  it('closes when the X is clicked', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/clock/', () => HttpResponse.json({ status: 'idle' })),
      http.get('*/api/projects/', () => HttpResponse.json([])),
    );
    renderFab();
    await waitFor(() => expect(screen.getByText('Clock')).toBeInTheDocument());
    const fab = screen.getAllByRole('button', { name: /clock in/i })[0];
    await user.click(fab);
    await user.click(screen.getByRole('button', { name: 'Close' }));
    await waitFor(() => expect(screen.queryByLabelText(/which venture/i)).toBeNull());
  });

  it('ticks the elapsed clock while active', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    server.use(
      http.get('*/api/clock/', () =>
        HttpResponse.json({
          status: 'active',
          clock_in: new Date(Date.now() - 1000).toISOString(),
          project_title: 'Tick',
        }),
      ),
    );
    renderFab();
    await waitFor(() => expect(screen.getByRole('button', { name: /clock out/i })).toBeInTheDocument());
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    vi.useRealTimers();
  });
});
