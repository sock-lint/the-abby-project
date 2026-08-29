import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen } from '../../test/render';
import { server } from '../../test/server';
import PrinterStatus from './PrinterStatus';

const PRINTER = { id: 1, name: 'X1C in the garage', is_active: true };

function stubStatus(body) {
  server.use(
    http.get(/\/api\/printers\/1\/status\/$/, () => HttpResponse.json(body)),
  );
}

describe('PrinterStatus', () => {
  it('reads offline when the listener has no snapshot', async () => {
    stubStatus({ printer: PRINTER, live: null, connected: false, job: null });
    renderWithProviders(<PrinterStatus printer={PRINTER} />);
    expect(await screen.findByText('Offline')).toBeInTheDocument();
    expect(screen.getByText(/listener isn’t connected/i)).toBeInTheDocument();
  });

  it('shows the running job with percent, layers and ETA', async () => {
    stubStatus({
      printer: PRINTER,
      live: { gcode_state: 'RUNNING', percent: 62 },
      connected: true,
      job: {
        id: 7, request: 42, request_title: 'Articulated Dragon',
        subtask_name: 'req-0042-articulated-dragon',
        state: 'running', state_display: 'Running',
        percent_complete: 62, layer_num: 120, total_layer_num: 300,
        remaining_minutes: 45, finished_at: null, events: [],
      },
    });
    renderWithProviders(<PrinterStatus printer={PRINTER} />);

    expect(await screen.findByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('Articulated Dragon')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: /print progress/i }))
      .toHaveAttribute('aria-valuenow', '62');
    expect(screen.getByText(/layer 120 of 300/)).toBeInTheDocument();
    expect(screen.getByText(/~45m left/)).toBeInTheDocument();
  });

  it('renders the job timeline with decoded printer alerts', async () => {
    stubStatus({
      printer: PRINTER,
      live: { gcode_state: 'RUNNING' },
      connected: true,
      job: {
        id: 7, request: 42, request_title: 'Articulated Dragon',
        subtask_name: 'req-0042-articulated-dragon',
        state: 'running', state_display: 'Running',
        percent_complete: 10, layer_num: 5, total_layer_num: 300,
        remaining_minutes: 120, finished_at: null,
        events: [
          {
            id: 1, kind: 'started', kind_display: 'Started',
            message: 'Started printing Articulated Dragon', code: '', severity: '',
            created_at: '2026-08-27T10:00:00Z', context: {},
          },
          {
            id: 2, kind: 'hms', kind_display: 'Printer alert',
            message: 'The filament ran out. Load a new spool.',
            code: '0300_0100_0002_0001', severity: 'serious',
            created_at: '2026-08-27T10:20:00Z', context: {},
          },
        ],
      },
    });
    renderWithProviders(<PrinterStatus printer={PRINTER} />);

    expect(
      await screen.findByText('The filament ran out. Load a new spool.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Printer alert')).toBeInTheDocument();
    expect(screen.getByText('Started printing Articulated Dragon')).toBeInTheDocument();
  });

  it('flags an open job that has not matched a request', async () => {
    stubStatus({
      printer: PRINTER,
      live: { gcode_state: 'RUNNING' },
      connected: true,
      job: {
        id: 8, request: null, request_title: null,
        subtask_name: 'benchy', state: 'running', state_display: 'Running',
        percent_complete: 4, layer_num: 2, total_layer_num: 100,
        remaining_minutes: 60, finished_at: null, events: [],
      },
    });
    renderWithProviders(<PrinterStatus printer={PRINTER} />);
    expect(await screen.findByText(/Not linked to a request yet/i)).toBeInTheDocument();
    expect(screen.getByText('benchy')).toBeInTheDocument();
  });

  it('shows the filament loaded in the AMS', async () => {
    stubStatus({
      printer: PRINTER,
      connected: true,
      job: null,
      live: {
        gcode_state: 'IDLE',
        filaments: [
          {
            slot: 'A1', material: 'PLA', label: 'PLA Basic',
            display_name: 'PLA Basic', hex: '#00AE42', remain_percent: 92,
            is_external: false,
          },
          {
            slot: 'Ext', material: 'TPU', label: '', display_name: 'TPU',
            hex: '#FF8800', remain_percent: null, is_external: true,
          },
        ],
      },
    });
    renderWithProviders(<PrinterStatus printer={PRINTER} />);

    expect(await screen.findByText('PLA Basic')).toBeInTheDocument();
    expect(screen.getByText('92%')).toBeInTheDocument();
    // The external spool is a filament source too — on a printer with no AMS
    // it is the only one.
    expect(screen.getByText('Ext')).toBeInTheDocument();
    expect(screen.getByText('TPU')).toBeInTheDocument();
  });

  it('renders no filament row when the AMS has not reported', async () => {
    stubStatus({
      printer: PRINTER, connected: true, job: null,
      live: { gcode_state: 'IDLE', filaments: [] },
    });
    const { container } = renderWithProviders(<PrinterStatus printer={PRINTER} />);
    await screen.findByText('Connected');
    expect(container.querySelector('[data-filament]')).toBeNull();
  });
});
