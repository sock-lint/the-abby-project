import { describe, expect, it } from 'vitest';
import { renderWithProviders, screen, waitFor, within } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import PrinterConfigPanel from './PrinterConfigPanel';

const PRINTER = {
  id: 1,
  name: 'X1C in the garage',
  serial: '01P00A000000001',
  model_name: 'X1C',
  transport: 'local',
  transport_display: 'Local MQTT (LAN)',
  host: '192.168.1.42',
  port: 8883,
  is_active: true,
  has_credentials: true,
};

describe('PrinterConfigPanel', () => {
  it('lists printers and flags the ones missing credentials', () => {
    renderWithProviders(
      <PrinterConfigPanel printers={[PRINTER, {
        ...PRINTER, id: 2, name: 'P1S upstairs', has_credentials: false,
      }]} />,
    );
    expect(screen.getByText('X1C in the garage')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByText('No credentials')).toBeInTheDocument();
  });

  it('prompts to add one when the family has no printer yet', () => {
    renderWithProviders(<PrinterConfigPanel printers={[]} />);
    expect(screen.getByText(/No printer registered yet/i)).toBeInTheDocument();
  });

  it('POSTs a new local printer with its access code', async () => {
    const spy = spyHandler('post', /\/api\/printers\/$/, { id: 3 });
    server.use(spy.handler);

    const { user } = renderWithProviders(<PrinterConfigPanel printers={[]} />);
    await user.click(screen.getByRole('button', { name: /add printer/i }));

    await user.type(await screen.findByLabelText('Name'), 'P1S upstairs');
    await user.type(screen.getByLabelText('Serial'), '01P00A000000002');
    await user.type(screen.getByLabelText('Host'), '192.168.1.50');
    await user.type(screen.getByLabelText(/access code/i), '12345678');
    // "Add printer" names both the panel's trigger and the sheet's submit —
    // scope to the dialog so the click can't land on the opener again.
    const sheet = screen.getByRole('dialog', { name: /add a printer/i });
    await user.click(within(sheet).getByRole('button', { name: 'Add printer' }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/printers\/$/);
    expect(spy.calls[0].body).toEqual({
      name: 'P1S upstairs',
      serial: '01P00A000000002',
      model_name: 'X1C',
      transport: 'local',
      host: '192.168.1.50',
      port: 8883,
      is_active: true,
      access_code: '12345678',
    });
  });

  it('omits blank credentials on edit so a rename cannot wipe the stored code', async () => {
    const spy = spyHandler('patch', /\/api\/printers\/1\/$/, { id: 1 });
    server.use(spy.handler);

    const { user } = renderWithProviders(<PrinterConfigPanel printers={[PRINTER]} />);
    await user.click(screen.getByRole('button', { name: 'Edit' }));

    const name = await screen.findByLabelText('Name');
    await user.clear(name);
    await user.type(name, 'X1C by the bikes');
    await user.click(screen.getByRole('button', { name: 'Save printer' }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/printers\/1\/$/);
    expect(spy.calls[0].body).toEqual({
      name: 'X1C by the bikes',
      serial: '01P00A000000001',
      model_name: 'X1C',
      transport: 'local',
      host: '192.168.1.42',
      port: 8883,
      is_active: true,
    });
    expect(spy.calls[0].body).not.toHaveProperty('access_code');
  });

  it('DELETEs the printer after the parent confirms', async () => {
    const spy = spyHandler('delete', /\/api\/printers\/1\/$/, { ok: true });
    server.use(spy.handler);

    const { user } = renderWithProviders(<PrinterConfigPanel printers={[PRINTER]} />);
    await user.click(screen.getByRole('button', { name: /remove X1C in the garage/i }));
    await user.click(await screen.findByRole('button', { name: 'Remove' }));

    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/printers\/1\/$/);
  });
});
