import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import {
  renderWithProviders, screen, userEvent, waitFor,
} from '../../test/render';
import { server } from '../../test/server';
import FilamentPicker from './FilamentPicker';

const PRINTERS = [{ id: 1, name: 'X1C', is_active: true }];

function stubFilaments(filaments, { id = 1 } = {}) {
  server.use(
    http.get(new RegExp(`/api/printers/${id}/status/$`), () => HttpResponse.json({
      printer: { id, name: 'X1C' },
      live: { gcode_state: 'IDLE', filaments },
      connected: true,
      job: null,
    })),
  );
}

const PLA = {
  slot: 'A1', material: 'PLA', label: 'PLA Basic', display_name: 'PLA Basic',
  hex: '#00AE42', remain_percent: 92, is_external: false,
};
const PETG = {
  slot: 'A2', material: 'PETG', label: '', display_name: 'PETG',
  hex: '#1E90FF', remain_percent: null, is_external: false,
};

describe('FilamentPicker', () => {
  it('offers what the AMS currently has loaded', async () => {
    stubFilaments([PLA, PETG]);
    renderWithProviders(
      <FilamentPicker printers={PRINTERS} value="" onSelect={() => {}} />,
    );

    expect(await screen.findByRole('button', { name: /A1 · PLA Basic/ }))
      .toBeInTheDocument();
    expect(screen.getByRole('button', { name: /A2 · PETG/ })).toBeInTheDocument();
  });

  it('hands the colour name up, never the slot', async () => {
    // A slot number is meaningless by the time the plate is sliced — bay A2
    // will be holding something else next week.
    const onSelect = vi.fn();
    stubFilaments([PLA]);
    renderWithProviders(
      <FilamentPicker printers={PRINTERS} value="" onSelect={onSelect} />,
    );

    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: /A1 · PLA Basic/ }));
    expect(onSelect).toHaveBeenCalledWith('PLA Basic');
  });

  it('renders nothing when the printer is asleep', async () => {
    // The snapshot expires five minutes after the listener stops reporting,
    // and kids ask for prints when the printer is off. "No filament found"
    // would read as a broken feature on a perfectly normal path.
    stubFilaments([]);
    const { container } = renderWithProviders(
      <FilamentPicker printers={PRINTERS} value="" onSelect={() => {}} />,
    );
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('renders nothing, and never errors, when the status call fails', async () => {
    server.use(
      http.get(/\/api\/printers\/1\/status\/$/, () => new HttpResponse(null, {
        status: 500,
      })),
    );
    const { container } = renderWithProviders(
      <FilamentPicker printers={PRINTERS} value="" onSelect={() => {}} />,
    );
    await waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('renders nothing when the family has no printer at all', async () => {
    const { container } = renderWithProviders(
      <FilamentPicker printers={[]} value="" onSelect={() => {}} />,
    );
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('marks the chip matching the typed colour as selected', async () => {
    stubFilaments([PLA, PETG]);
    renderWithProviders(
      <FilamentPicker printers={PRINTERS} value="PLA Basic" onSelect={() => {}} />,
    );

    const chip = await screen.findByRole('button', { name: /A1 · PLA Basic/ });
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: /A2 · PETG/ }))
      .toHaveAttribute('aria-pressed', 'false');
  });

  it('shows one chip when two printers hold the same spool', async () => {
    stubFilaments([PLA]);
    stubFilaments([{ ...PLA, slot: 'A3' }], { id: 2 });
    renderWithProviders(
      <FilamentPicker
        printers={[...PRINTERS, { id: 2, name: 'P1S', is_active: true }]}
        value=""
        onSelect={() => {}}
      />,
    );

    await screen.findByRole('button', { name: /PLA Basic/ });
    expect(screen.getAllByRole('button', { name: /PLA Basic/ })).toHaveLength(1);
  });

  it('ignores a printer the parent has deactivated', async () => {
    stubFilaments([PLA]);
    const { container } = renderWithProviders(
      <FilamentPicker
        printers={[{ id: 1, name: 'X1C', is_active: false }]}
        value=""
        onSelect={() => {}}
      />,
    );
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });
});
