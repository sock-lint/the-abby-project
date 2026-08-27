import { describe, expect, it } from 'vitest';
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
});
