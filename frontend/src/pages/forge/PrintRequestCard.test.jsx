import { describe, expect, it } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import PrintRequestCard from './PrintRequestCard';

function buildRequest(over = {}) {
  return {
    id: 42,
    user: 1,
    user_name: 'Abby',
    username: 'abby',
    title: 'Articulated Dragon',
    source_kind: 'makerworld',
    source_url: 'https://makerworld.com/en/models/1',
    thumbnail: null,
    color: 'glow in the dark green',
    reason: 'It is a present for Nana.',
    needed_by: '2026-09-04',
    status: 'pending',
    parent_notes: '',
    slug: '',
    plate_filename: '',
    latest_job: null,
    ...over,
  };
}

describe('PrintRequestCard', () => {
  it('renders a pending request with its colour, needed-by and reason', () => {
    renderWithProviders(<PrintRequestCard request={buildRequest()} />);
    expect(screen.getByText('Articulated Dragon')).toBeInTheDocument();
    expect(screen.getByText(/glow in the dark green/i)).toBeInTheDocument();
    expect(screen.getByText(/It is a present for Nana/)).toBeInTheDocument();
    expect(screen.getByText('Pending')).toBeInTheDocument();
  });

  it('shows a placeholder instead of a broken image when there is no thumbnail', () => {
    const { container } = renderWithProviders(
      <PrintRequestCard request={buildRequest()} />,
    );
    expect(container.querySelector('img')).toBeNull();
  });

  it('renders the thumbnail when the request has one', () => {
    const { container } = renderWithProviders(
      <PrintRequestCard request={buildRequest({ thumbnail: '/media/thumbs/x.png' })} />,
    );
    expect(container.querySelector('img')).toHaveAttribute('src', '/media/thumbs/x.png');
  });

  it('renders the minted plate filename prominently once approved', () => {
    renderWithProviders(
      <PrintRequestCard
        request={buildRequest({
          status: 'approved',
          slug: 'req-0042-articulated-dragon',
          plate_filename: 'req-0042-articulated-dragon.3mf',
        })}
      />,
    );
    expect(screen.getByText('req-0042-articulated-dragon.3mf')).toBeInTheDocument();
    expect(screen.getByText(/Save the sliced plate as/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /copy plate filename/i }),
    ).toBeInTheDocument();
  });

  it('copies the plate filename to the clipboard', async () => {
    // userEvent.setup() installs its own navigator.clipboard stub, so read
    // the value back through it rather than mocking writeText ourselves.
    const { user } = renderWithProviders(
      <PrintRequestCard
        request={buildRequest({ status: 'approved', plate_filename: 'req-0042-dragon.3mf' })}
      />,
    );
    await user.click(screen.getByRole('button', { name: /copy plate filename/i }));
    expect(await screen.findByText('Copied')).toBeInTheDocument();
    await expect(navigator.clipboard.readText()).resolves.toBe('req-0042-dragon.3mf');
  });

  it('shows live progress while a job is running', () => {
    renderWithProviders(
      <PrintRequestCard
        request={buildRequest({
          status: 'printing',
          plate_filename: 'req-0042-dragon.3mf',
          latest_job: {
            id: 7, state: 'running', percent_complete: 62,
            layer_num: 120, total_layer_num: 300, remaining_minutes: 45,
            failure_reason: null, started_at: '2026-08-27T10:00:00Z', finished_at: null,
          },
        })}
      />,
    );
    const bar = screen.getByRole('progressbar', { name: /print progress/i });
    expect(bar).toHaveAttribute('aria-valuenow', '62');
    expect(screen.getByText('62% · layer 120 of 300 · ~45m left')).toBeInTheDocument();
  });

  it('shows the decoded failure sentence, never a raw code', () => {
    renderWithProviders(
      <PrintRequestCard
        request={buildRequest({
          status: 'failed',
          latest_job: {
            id: 8, state: 'failed', percent_complete: 18,
            layer_num: 20, total_layer_num: 300, remaining_minutes: null,
            failure_reason: 'The nozzle is clogged. Clear it and try again.',
            started_at: '2026-08-27T10:00:00Z', finished_at: '2026-08-27T10:40:00Z',
          },
        })}
      />,
    );
    expect(
      screen.getByText('The nozzle is clogged. Clear it and try again.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/0300_0100/)).not.toBeInTheDocument();
  });

  it('hides the decide/cancel actions unless the caller allows them', () => {
    const { unmount } = renderWithProviders(
      <PrintRequestCard request={buildRequest()} />,
    );
    expect(screen.queryByRole('button', { name: 'Decide' })).not.toBeInTheDocument();
    unmount();

    renderWithProviders(
      <PrintRequestCard request={buildRequest()} canDecide canCancel />,
    );
    expect(screen.getByRole('button', { name: 'Decide' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });
});
