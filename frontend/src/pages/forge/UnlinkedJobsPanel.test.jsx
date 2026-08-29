import { describe, expect, it } from 'vitest';
import { HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import UnlinkedJobsPanel from './UnlinkedJobsPanel';

const JOB = {
  id: 9,
  printer: 1,
  printer_name: 'X1C in the garage',
  request: null,
  subtask_name: 'benchy_plate_1',
  state: 'finished',
  state_display: 'Finished',
  started_at: '2026-08-26T18:00:00Z',
};

const REQUESTS = [
  { id: 3, title: 'Articulated Dragon', status: 'approved', user_name: 'Abby' },
  { id: 4, title: 'Rejected thing', status: 'rejected', user_name: 'Abby' },
];

describe('UnlinkedJobsPanel', () => {
  it('lists unmatched prints with their printer', () => {
    renderWithProviders(<UnlinkedJobsPanel jobs={[JOB]} requests={REQUESTS} />);
    expect(screen.getByText('benchy_plate_1')).toBeInTheDocument();
    expect(screen.getByText(/X1C in the garage/)).toBeInTheDocument();
  });

  it('says so when every print found its request', () => {
    renderWithProviders(<UnlinkedJobsPanel jobs={[]} requests={REQUESTS} />);
    expect(screen.getByText(/Nothing to link/i)).toBeInTheDocument();
  });

  it('offers only bindable requests in the picker', async () => {
    const { user } = renderWithProviders(
      <UnlinkedJobsPanel jobs={[JOB]} requests={REQUESTS} />,
    );
    await user.click(screen.getByRole('button', { name: /link to request/i }));

    expect(
      await screen.findByRole('button', { name: /Articulated Dragon/ }),
    ).toBeInTheDocument();
    // A rejected request must never absorb a print.
    expect(screen.queryByRole('button', { name: /Rejected thing/ })).not.toBeInTheDocument();
  });

  it('POSTs request_id to the job link endpoint', async () => {
    const spy = spyHandler('post', /\/api\/print-jobs\/9\/link\/$/, { id: 9, request: 3 });
    server.use(spy.handler);

    const { user } = renderWithProviders(
      <UnlinkedJobsPanel jobs={[JOB]} requests={REQUESTS} />,
    );
    await user.click(screen.getByRole('button', { name: /link to request/i }));
    await user.click(await screen.findByRole('button', { name: /Articulated Dragon/ }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/print-jobs\/9\/link\/$/);
    expect(spy.calls[0].body).toEqual({ request_id: 3 });
  });

  it('POSTs to dismiss and tells the page to refetch', async () => {
    const spy = spyHandler('post', /\/api\/print-jobs\/9\/dismiss\/$/, { id: 9 });
    server.use(spy.handler);
    let changed = 0;

    const { user } = renderWithProviders(
      <UnlinkedJobsPanel
        jobs={[JOB]}
        requests={REQUESTS}
        onChanged={() => { changed += 1; }}
      />,
    );
    await user.click(screen.getByRole('button', { name: /dismiss benchy_plate_1/i }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/print-jobs\/9\/dismiss\/$/);
    await waitFor(() => expect(changed).toBe(1));
  });

  it('confirms before deleting, and does not call until confirmed', async () => {
    const spy = spyHandler('delete', /\/api\/print-jobs\/9\/$/, null);
    server.use(spy.handler);

    const { user } = renderWithProviders(
      <UnlinkedJobsPanel jobs={[JOB]} requests={REQUESTS} onChanged={() => {}} />,
    );
    await user.click(screen.getByRole('button', { name: /delete benchy_plate_1/i }));

    const dialog = await screen.findByRole('alertdialog', { name: /delete this print/i });
    expect(dialog).toBeInTheDocument();
    // Nothing has gone to the server yet — the dialog is the whole point.
    expect(spy.calls).toHaveLength(0);

    await user.click(screen.getByRole('button', { name: /^delete$/i }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].method).toBe('DELETE');
  });

  it('cancelling the delete dialog leaves the print alone', async () => {
    const spy = spyHandler('delete', /\/api\/print-jobs\/9\/$/, null);
    server.use(spy.handler);

    const { user } = renderWithProviders(
      <UnlinkedJobsPanel jobs={[JOB]} requests={REQUESTS} onChanged={() => {}} />,
    );
    await user.click(screen.getByRole('button', { name: /delete benchy_plate_1/i }));
    await screen.findByRole('alertdialog', { name: /delete this print/i });
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(spy.calls).toHaveLength(0);
    expect(screen.getByText('benchy_plate_1')).toBeInTheDocument();
  });

  it('hides cleared prints behind a toggle and restores one', async () => {
    // A dismiss nobody can undo is just a delete that lies about it, so the
    // way back has to exist in the UI, not only in the admin.
    const cleared = { ...JOB, id: 12, subtask_name: 'old_plate', dismissed_at: '2026-08-27T10:00:00Z' };
    const spy = spyHandler('post', /\/api\/print-jobs\/12\/restore\/$/, { id: 12 });
    server.use(spy.handler);

    const { user } = renderWithProviders(
      <UnlinkedJobsPanel
        jobs={[JOB]}
        dismissedJobs={[cleared]}
        requests={REQUESTS}
        onChanged={() => {}}
      />,
    );
    expect(screen.queryByText('old_plate')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /show 1 cleared print/i }));
    expect(screen.getByText('old_plate')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /restore/i }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/print-jobs\/12\/restore\/$/);
  });

  it('offers no cleared toggle when nothing has been dismissed', () => {
    renderWithProviders(<UnlinkedJobsPanel jobs={[JOB]} requests={REQUESTS} />);
    expect(screen.queryByRole('button', { name: /cleared print/i })).not.toBeInTheDocument();
  });

  it('surfaces a refused dismiss instead of silently doing nothing', async () => {
    // The server refuses a running or linked job; the parent has to see why.
    server.use(spyHandler('post', /\/api\/print-jobs\/9\/dismiss\/$/, () =>
      HttpResponse.json(
        { error: 'That print is still running — wait for it to finish.' },
        { status: 400 },
      )).handler);

    const { user } = renderWithProviders(
      <UnlinkedJobsPanel jobs={[JOB]} requests={REQUESTS} onChanged={() => {}} />,
    );
    await user.click(screen.getByRole('button', { name: /dismiss benchy_plate_1/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/still running/i);
  });
});
