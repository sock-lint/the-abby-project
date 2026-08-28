import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
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

  it('says which field is blank instead of leaving the badge a dead end', () => {
    renderWithProviders(
      <PrinterConfigPanel printers={[{
        ...PRINTER,
        has_credentials: false,
        missing_credentials: ['access_code'],
        credential_hint: "No LAN access code saved — the access code is on the "
          + 'printer’s screen under Settings → Network.',
      }]} />,
    );
    expect(screen.getByText(/Settings → Network/)).toBeInTheDocument();
  });

  it('falls back to the listener’s own complaint once credentials are set', () => {
    renderWithProviders(
      <PrinterConfigPanel printers={[{
        ...PRINTER, credential_hint: '', last_error: 'Connection refused.',
      }]} />,
    );
    expect(screen.getByText('Connection refused.')).toBeInTheDocument();
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

  it('hangs a rejected access code under its own input, not in a JSON blob', async () => {
    // The server refuses an incomplete printer, and DRF answers with
    // {access_code: [...]}. Without the field mapping that body falls through
    // to the client's JSON.stringify fallback and the parent reads raw JSON.
    server.use(http.post(/\/api\/printers\/$/, () => HttpResponse.json(
      { access_code: ['Enter the printer’s LAN access code — it’s on the printer’s screen under Settings → Network.'] },
      { status: 400 },
    )));

    const { user } = renderWithProviders(<PrinterConfigPanel printers={[]} />);
    await user.click(screen.getByRole('button', { name: /add printer/i }));
    await user.type(await screen.findByLabelText('Name'), 'P1S upstairs');
    await user.type(screen.getByLabelText('Serial'), '01P00A000000002');
    const sheet = screen.getByRole('dialog', { name: /add a printer/i });
    await user.click(within(sheet).getByRole('button', { name: 'Add printer' }));

    const message = await screen.findByText(/LAN access code/);
    expect(message).toBeInTheDocument();
    // The input owns the message, so a screen reader reads it with the field.
    expect(screen.getByLabelText(/access code/i).getAttribute('aria-describedby'))
      .toContain(message.getAttribute('id'));
    expect(screen.queryByText(/^\{/)).not.toBeInTheDocument();
    // The sheet stays open so the parent can fix it in place.
    expect(screen.getByRole('dialog', { name: /add a printer/i })).toBeInTheDocument();
  });

  it('banners a rejection that has no input to hang on', async () => {
    server.use(http.post(/\/api\/printers\/$/, () => HttpResponse.json(
      { detail: 'You do not have permission to perform this action.' },
      { status: 403 },
    )));

    const { user } = renderWithProviders(<PrinterConfigPanel printers={[]} />);
    await user.click(screen.getByRole('button', { name: /add printer/i }));
    await user.type(await screen.findByLabelText('Name'), 'P1S upstairs');
    const sheet = screen.getByRole('dialog', { name: /add a printer/i });
    await user.click(within(sheet).getByRole('button', { name: 'Add printer' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/do not have permission/i);
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
