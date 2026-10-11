import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Payments from '../Payments';
import { AuthProvider, useAuth } from '../../hooks/useApi';
import { server } from '../../test/server';
import { buildParent, buildUser } from '../../test/factories';
import { spyHandler } from '../../test/spy';
import GreenlightWorkflow from './GreenlightWorkflow';

const children = [
  { id: 7, username: 'abby', display_name: 'Abby', role: 'child' },
  { id: 8, username: 'beck', display_name: 'Beck', role: 'child' },
];
const csv = 'date,amount,description,reference,type\n2026-10-10,10.00,Weekly work,gl-10,transfer\n2026-10-11,-4.00,Shop purchase,gl-11,purchase\n2026-10-11,5.00,Extra earnings,gl-12,transfer';
const rows = [
  { row_number: 2, fingerprint: 'first', date: '2026-10-10', amount: '10.00', description: 'Weekly work', reference: 'gl-10', transaction_type: 'transfer', eligible: true, duplicate: false, error: null, match_candidates: [55] },
  { row_number: 3, fingerprint: 'purchase', date: '2026-10-11', amount: '-4.00', description: 'Shop purchase', reference: 'gl-11', transaction_type: 'purchase', eligible: false, duplicate: false, error: null, match_candidates: [] },
  { row_number: 4, fingerprint: 'third', date: '2026-10-11', amount: '5.00', description: 'Extra earnings', reference: 'gl-12', transaction_type: 'transfer', eligible: true, duplicate: false, error: null, match_candidates: [] },
];
function overview(overrides = {}) {
  return {
    user_id: 7, owed_balance: '25.00', approved_payable: '20.00', pending_hourly: '5.00',
    balance_snapshot: { id: 2, user: 7, amount: '100.00', as_of: '2026-10-10T19:00:00Z', memo: 'Checked card and savings', created_by: 1, created_at: '2026-10-10T19:01:00Z' },
    approved_timecards: [{ id: 12, week_start: '2026-10-04', total_earnings: '20.00' }],
    payouts: [{ id: 55, amount: '10.00', transferred_on: '2026-10-10', reference: '', memo: 'Last payout', timecard: null, source: 'manual', reconciled: false, created_by: 1, created_at: '2026-10-10T19:00:00Z' }],
    ...overrides,
  };
}
function renderWorkflow({ data = overview(), parent = true, extra = [] } = {}) {
  const changed = vi.fn();
  server.use(
    http.get('*/api/payments/greenlight/overview/', () => HttpResponse.json(data)),
    ...extra,
  );
  const mounted = render(<GreenlightWorkflow userId={7} kidName="Abby" isParent={parent} ownerKey="parent:family:7" onLedgerChanged={changed} />);
  return { user: userEvent.setup(), changed, ...mounted };
}
function renderPage({ role = buildParent(), initial = '/payments?kid=7', extra = [], additional } = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(role)),
    http.get('*/api/children/', () => HttpResponse.json(children)),
    http.get('*/api/balance/', () => HttpResponse.json({ balance: '25.00', breakdown: {}, recent_transactions: [] })),
    http.get('*/api/payments/greenlight/overview/', ({ request }) => {
      const childId = Number(new URL(request.url).searchParams.get('user_id'));
      return HttpResponse.json(overview({ user_id: childId }));
    }),
  );
  server.use(...extra);
  render(<MemoryRouter initialEntries={[initial]}><AuthProvider><Payments />{additional}</AuthProvider></MemoryRouter>);
  return userEvent.setup();
}
async function openTransfer(user) {
  await user.click(await screen.findByRole('button', { name: /^record completed transfer$/i }));
  return within(await screen.findByRole('dialog'));
}

describe('Greenlight payout workflow', () => {
  beforeEach(() => sessionStorage.clear());
  it('keeps money owed separate from a dated parent-verified balance', async () => {
    renderPage();
    expect(await screen.findByText('$25.00')).toBeInTheDocument();
    expect(await screen.findByText('$100.00')).toBeInTheDocument();
    expect(screen.getByText(/money still owed$/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /last parent-verified greenlight balance/i })).toBeInTheDocument();
    expect(screen.getByText(/as of/i)).toBeInTheDocument();
    expect(screen.getByText(/\$5.00 in hourly earnings awaiting approval/i)).toBeInTheDocument();
    expect(screen.queryByText(/current balance/i)).not.toBeInTheDocument();
  });

  it('starts an unknown bank balance as unknown, never lifetime payouts', async () => {
    renderWorkflow({ data: overview({ balance_snapshot: null }) });
    expect(await screen.findByText(/unknown.*no greenlight balance has been verified/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /recorded payouts/i })).toBeInTheDocument();
  });

  it('records only an already-completed transfer and reuses the same key after an uncertain save', async () => {
    let attempts = 0;
    const payout = spyHandler('post', /\/api\/payments\/greenlight\/payout\/$/, () => {
      attempts += 1;
      return attempts === 1 ? HttpResponse.json({ error: 'Save response was not confirmed.' }, { status: 503 }) : { created: false, payout: { id: 56 } };
    });
    const { user, changed } = renderWorkflow({ extra: [payout.handler] });
    const dialog = await openTransfer(user);
    const amount = dialog.getByLabelText('Transfer amount');
    await user.clear(amount);
    await user.type(amount, '5.00');
    await user.clear(dialog.getByLabelText('Transferred on'));
    await user.type(dialog.getByLabelText('Transferred on'), '2026-10-11');
    await user.type(dialog.getByLabelText('Greenlight reference (optional)'), 'gl-100');
    await user.type(dialog.getByLabelText('Transfer memo (optional)'), 'Weekend work');
    const submit = dialog.getByRole('button', { name: /^record completed transfer$/i });
    expect(submit).toBeDisabled();
    await user.click(dialog.getByRole('checkbox', { name: /already completed/i }));
    await user.click(submit);
    expect(await dialog.findByText(/save response was not confirmed/i)).toBeInTheDocument();
    expect(changed).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Transfer memo (optional)')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Transfer memo (optional)'), { target: { value: 'different memo' } });
    expect(screen.getByLabelText('Transfer memo (optional)')).toHaveValue('Weekend work');
    await user.click(screen.getByRole('button', { name: /retry recording this transfer/i }));
    await waitFor(() => expect(payout.calls).toHaveLength(2));
    expect(payout.calls[0].url).toMatch(/\/api\/payments\/greenlight\/payout\/$/);
    expect(payout.calls[0].body).toEqual({
      user_id: 7, amount: '5', transferred_on: '2026-10-11', reference: 'gl-100', memo: 'Weekend work',
      idempotency_key: expect.stringMatching(/^[0-9a-f-]{36}$/i), timecard_id: null,
    });
    expect(payout.calls[1].body).toEqual(payout.calls[0].body);
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
    expect(screen.getByText('$100.00')).toBeInTheDocument();
  });

  it('records the full approved timecard amount with its saved id', async () => {
    const payout = spyHandler('post', /\/api\/payments\/greenlight\/payout\/$/, { created: true, payout: { id: 56 } });
    const { user } = renderWorkflow({ extra: [payout.handler] });
    const dialog = await openTransfer(user);
    await user.selectOptions(dialog.getByLabelText(/approved timecard/i), '12');
    expect(dialog.getByLabelText('Transfer amount')).toHaveValue(20);
    expect(dialog.getByLabelText('Transfer amount')).toHaveAttribute('readonly');
    await user.click(dialog.getByRole('checkbox', { name: /already completed/i }));
    await user.click(dialog.getByRole('button', { name: /^record completed transfer$/i }));
    await waitFor(() => expect(payout.calls).toHaveLength(1));
    expect(payout.calls[0].body).toEqual({
      user_id: 7, amount: '20.00', transferred_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
      reference: '', memo: '', idempotency_key: expect.any(String), timecard_id: 12,
    });
    expect(payout.calls[0].url).toMatch(/\/api\/payments\/greenlight\/payout\/$/);
  });

  it('resumes the same uncertain transfer after closing and after a page remount', async () => {
    let attempts = 0;
    const payout = spyHandler('post', /\/api\/payments\/greenlight\/payout\/$/, () => {
      attempts += 1;
      return attempts === 1 ? HttpResponse.json({ error: 'Transfer response timed out.' }, { status: 408 }) : { created: false, payout: { id: 56 } };
    });
    const first = renderWorkflow({ extra: [payout.handler] });
    let dialog = await openTransfer(first.user);
    await first.user.click(dialog.getByRole('checkbox', { name: /already completed/i }));
    await first.user.click(dialog.getByRole('button', { name: /^record completed transfer$/i }));
    await screen.findByText(/transfer response timed out/i);
    await first.user.click(screen.getByRole('button', { name: /^cancel$/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    dialog = await openTransfer(first.user);
    expect(dialog.getByLabelText('Transfer amount')).toBeDisabled();
    expect(dialog.getByRole('button', { name: /retry recording this transfer/i })).toBeEnabled();
    first.unmount();
    const second = renderWorkflow({ extra: [payout.handler] });
    dialog = await openTransfer(second.user);
    expect(dialog.getByLabelText('Transfer amount')).toBeDisabled();
    await second.user.click(dialog.getByRole('button', { name: /retry recording this transfer/i }));
    await waitFor(() => expect(payout.calls).toHaveLength(2));
    expect(payout.calls[1].body).toEqual(payout.calls[0].body);
    await waitFor(() => expect(second.changed).toHaveBeenCalledTimes(1));
    expect(sessionStorage.getItem('abby_greenlight_pending_transfer:parent:family:7')).toBeNull();
  });

  it('ignores a pending transfer draft belonging to another child', async () => {
    sessionStorage.setItem('abby_greenlight_pending_transfer:parent:family:7', JSON.stringify({ payload: {
      user_id: 8, amount: '99.00', idempotency_key: 'other-child', transferred_on: '2026-10-10',
    } }));
    const { user } = renderWorkflow();
    const dialog = await openTransfer(user);
    expect(dialog.getByLabelText('Transfer amount')).toHaveValue(20);
    expect(dialog.getByLabelText('Transfer amount')).not.toBeDisabled();
    expect(dialog.getByRole('checkbox', { name: /already completed/i })).not.toBeChecked();
  });

  it('requires review before discarding a persisted conflict and gives a different transfer a new key', async () => {
    let attempts = 0;
    const payout = spyHandler('post', /\/api\/payments\/greenlight\/payout\/$/, () => {
      attempts += 1;
      return attempts === 1
        ? HttpResponse.json({ error: 'This reference belongs to another recorded payout.' }, { status: 409 })
        : { created: true, payout: { id: 56 } };
    });
    const { user, changed } = renderWorkflow({ extra: [payout.handler] });
    let dialog = await openTransfer(user);
    await user.type(dialog.getByLabelText('Greenlight reference (optional)'), 'older-reference');
    await user.click(dialog.getByRole('checkbox', { name: /already completed/i }));
    await user.click(dialog.getByRole('button', { name: /^record completed transfer$/i }));
    await screen.findByText(/reference belongs to another recorded payout/i);
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    dialog = await openTransfer(user);
    expect(dialog.getByRole('button', { name: /retry recording this transfer/i })).toBeDisabled();
    const discard = dialog.getByRole('button', { name: /discard conflicting transfer draft/i });
    expect(discard).toBeDisabled();
    await user.click(dialog.getByRole('checkbox', { name: /checked the recorded payouts.*different completed transfer/i }));
    await user.click(discard);
    expect(dialog.getByLabelText('Transfer amount')).toBeEnabled();
    expect(dialog.getByLabelText('Greenlight reference (optional)')).toHaveValue('');
    expect(dialog.getByRole('checkbox', { name: /already completed/i })).not.toBeChecked();
    expect(sessionStorage.getItem('abby_greenlight_pending_transfer:parent:family:7')).toBeNull();
    await user.type(dialog.getByLabelText('Transfer amount'), '10');
    await user.type(dialog.getByLabelText('Greenlight reference (optional)'), 'new-reference');
    await user.click(dialog.getByRole('checkbox', { name: /already completed/i }));
    await user.click(dialog.getByRole('button', { name: /^record completed transfer$/i }));
    await waitFor(() => expect(payout.calls).toHaveLength(2));
    expect(payout.calls[1].body.idempotency_key).not.toBe(payout.calls[0].body.idempotency_key);
    expect(payout.calls[1].body).toEqual({
      user_id: 7, amount: '10', reference: 'new-reference', memo: '',
      timecard_id: null, transferred_on: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/), idempotency_key: expect.any(String),
    });
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  });

  it('maps transfer validation errors to the amount field and preserves the draft', async () => {
    const payout = spyHandler('post', /\/api\/payments\/greenlight\/payout\/$/, HttpResponse.json({ amount: ['Exceeds approved earnings.'] }, { status: 400 }));
    const { user } = renderWorkflow({ extra: [payout.handler] });
    const dialog = await openTransfer(user);
    await user.click(dialog.getByRole('checkbox', { name: /already completed/i }));
    await user.click(dialog.getByRole('button', { name: /^record completed transfer$/i }));
    expect(await dialog.findByText('Exceeds approved earnings.')).toBeInTheDocument();
    expect(dialog.getByLabelText('Transfer amount')).toHaveAttribute('aria-invalid', 'true');
    expect(dialog.getByLabelText('Transfer amount')).toHaveValue(20);
    expect(payout.calls).toHaveLength(1);
  });

  it('saves an observed balance and timestamp without changing the money ledger', async () => {
    const snapshot = spyHandler('post', /\/api\/payments\/greenlight\/snapshot\/$/, { id: 3 });
    const { user, changed } = renderWorkflow({ extra: [snapshot.handler] });
    await user.click(await screen.findByRole('button', { name: /verify greenlight balance/i }));
    const dialog = within(await screen.findByRole('dialog'));
    await user.type(dialog.getByLabelText('Verified Greenlight balance'), '81.25');
    await user.clear(dialog.getByLabelText('Observed at'));
    await user.type(dialog.getByLabelText('Observed at'), '2026-10-11T12:30');
    await user.type(dialog.getByLabelText('Balance memo (optional)'), 'Card balance checked');
    await user.click(dialog.getByRole('button', { name: /save verified balance/i }));
    await waitFor(() => expect(snapshot.calls).toHaveLength(1));
    expect(snapshot.calls[0].url).toMatch(/\/api\/payments\/greenlight\/snapshot\/$/);
    expect(snapshot.calls[0].body).toEqual({ user_id: 7, amount: '81.25', as_of: new Date('2026-10-11T12:30').toISOString(), memo: 'Card balance checked' });
    expect(changed).not.toHaveBeenCalled();
    expect(await screen.findByText(/snapshot saved/i)).toBeInTheDocument();
  });

  it('previews then atomically reconciles explicitly selected new and existing payouts, preserving selections after failure', async () => {
    const preview = spyHandler('post', /\/api\/payments\/greenlight\/preview\/$/, { rows, schema: ['date', 'amount', 'description', 'reference', 'type'] });
    let attempts = 0;
    const reconcile = spyHandler('post', /\/api\/payments\/greenlight\/reconcile\/$/, () => {
      attempts += 1;
      return attempts === 1 ? HttpResponse.json({ error: 'Payout changed; retry reconciliation.' }, { status: 409 }) : { recorded: 1, matched: 1, duplicates: 0 };
    });
    const { user, changed } = renderWorkflow({ extra: [preview.handler, reconcile.handler] });
    await user.click(await screen.findByLabelText('Or paste transfer CSV'));
    await user.paste(csv);
    await user.click(screen.getByRole('button', { name: /^preview csv$/i }));
    await waitFor(() => expect(preview.calls).toHaveLength(1));
    expect(preview.calls[0].url).toMatch(/\/api\/payments\/greenlight\/preview\/$/);
    expect(preview.calls[0].body).toEqual({ user_id: 7, csv_data: csv });
    const first = await screen.findByLabelText('Action for row 2');
    expect(first).toHaveValue('ignore');
    expect(screen.getByRole('button', { name: /reconcile 0 selected/i })).toBeDisabled();
    expect(screen.queryByLabelText('Action for row 3')).not.toBeInTheDocument();
    await user.selectOptions(first, '55');
    await user.selectOptions(screen.getByLabelText('Action for row 4'), 'record');
    const confirm = screen.getByRole('checkbox', { name: /these 2 selected transfers paid abby/i });
    await user.click(confirm);
    await user.click(screen.getByRole('button', { name: /reconcile 2 selected/i }));
    expect(await screen.findByText(/payout changed/i)).toBeInTheDocument();
    expect(changed).not.toHaveBeenCalled();
    expect(first).toHaveValue('55');
    expect(confirm).toBeChecked();
    await user.click(screen.getByRole('button', { name: /reconcile 2 selected/i }));
    await waitFor(() => expect(reconcile.calls).toHaveLength(2));
    const expected = { user_id: 7, csv_data: csv, selections: [
      { fingerprint: 'first', match_payment_id: 55, timecard_id: null },
      { fingerprint: 'third', match_payment_id: null, timecard_id: null },
    ] };
    expect(reconcile.calls[0].url).toMatch(/\/api\/payments\/greenlight\/reconcile\/$/);
    expect(reconcile.calls[0].body).toEqual(expected);
    expect(reconcile.calls[1].body).toEqual(expected);
    expect(await screen.findByText(/1 new payouts, 1 matched transfers/i)).toBeInTheDocument();
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  });

  it('disables already reconciled rows and invalidates a preview when the CSV changes', async () => {
    const preview = spyHandler('post', /\/api\/payments\/greenlight\/preview\/$/, { rows: [{ ...rows[0], duplicate: true }] });
    const { user } = renderWorkflow({ extra: [preview.handler] });
    const input = await screen.findByLabelText('Or paste transfer CSV');
    await user.click(input);
    await user.paste(csv);
    await user.click(screen.getByRole('button', { name: /^preview csv$/i }));
    expect(await screen.findByText(/already reconciled.*no additional payout/i)).toBeInTheDocument();
    expect(screen.queryByLabelText('Action for row 2')).not.toBeInTheDocument();
    await user.type(input, '\n');
    expect(screen.queryByText(/already reconciled.*no additional payout/i)).not.toBeInTheDocument();
  });

  it('associates a new imported payout with a chosen full approved timecard', async () => {
    const preview = spyHandler('post', /\/api\/payments\/greenlight\/preview\/$/, { rows: [{ ...rows[0], amount: '20.00' }] });
    const reconcile = spyHandler('post', /\/api\/payments\/greenlight\/reconcile\/$/, { recorded: 1, matched: 0, duplicates: 0 });
    const { user } = renderWorkflow({ extra: [preview.handler, reconcile.handler] });
    await user.click(await screen.findByLabelText('Or paste transfer CSV'));
    await user.paste(csv);
    await user.click(screen.getByRole('button', { name: /^preview csv$/i }));
    await user.selectOptions(await screen.findByLabelText('Action for row 2'), 'record');
    await user.selectOptions(screen.getByLabelText('Timecard for row 2 (optional)'), '12');
    await user.click(screen.getByRole('checkbox', { name: /these 1 selected transfers paid abby/i }));
    await user.click(screen.getByRole('button', { name: /reconcile 1 selected/i }));
    await waitFor(() => expect(reconcile.calls).toHaveLength(1));
    expect(reconcile.calls[0].body).toEqual({ user_id: 7, csv_data: csv, selections: [{ fingerprint: 'first', match_payment_id: null, timecard_id: 12 }] });
  });

  it('accepts a labelled CSV upload and previews its bytes', async () => {
    const preview = spyHandler('post', /\/api\/payments\/greenlight\/preview\/$/, { rows: [], schema: [] });
    const { user } = renderWorkflow({ extra: [preview.handler] });
    const file = new File([csv], 'greenlight.csv', { type: 'text/csv' });
    Object.defineProperty(file, 'text', { value: () => Promise.resolve(csv) });
    await user.upload(await screen.findByLabelText('Upload transfer CSV'), file);
    await waitFor(() => expect(screen.getByLabelText('Or paste transfer CSV')).toHaveValue(csv));
    await user.click(screen.getByRole('button', { name: /^preview csv$/i }));
    await waitFor(() => expect(preview.calls).toHaveLength(1));
    expect(preview.calls[0].body).toEqual({ user_id: 7, csv_data: csv });
  });

  it('rejects oversized uploads before a preview request', async () => {
    const preview = spyHandler('post', /\/api\/payments\/greenlight\/preview\/$/, { rows: [] });
    const { user } = renderWorkflow({ extra: [preview.handler] });
    const file = new File([''], 'large.csv', { type: 'text/csv' });
    Object.defineProperty(file, 'size', { value: 512 * 1024 + 1 });
    await user.upload(await screen.findByLabelText('Upload transfer CSV'), file);
    expect(await screen.findByText(/no larger than 512 kb/i)).toBeInTheDocument();
    expect(preview.calls).toHaveLength(0);
    expect(screen.getByRole('button', { name: /^preview csv$/i })).toBeDisabled();
  });

  it('lets children read their summary without import, snapshot or payout controls', async () => {
    renderWorkflow({ parent: false });
    expect(await screen.findByText('$100.00')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /record completed transfer/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /verify greenlight balance/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /preview csv/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Upload transfer CSV')).not.toBeInTheDocument();
  });

  it('requires an explicit child selection for parent Greenlight writes', async () => {
    const user = renderPage({ initial: '/payments' });
    await screen.findByText('$25.00');
    expect(screen.queryByRole('button', { name: /record completed transfer/i })).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Kid for payments and Greenlight'), '7');
    expect(await screen.findByRole('region', { name: /greenlight for abby/i })).toBeInTheDocument();
  });

  it('discards a late previous-child overview when the selected child changes', async () => {
    let release;
    const delayed = new Promise((resolve) => { release = resolve; });
    let started = false;
    const user = renderPage({ extra: [
      http.get('*/api/balance/', ({ request }) => HttpResponse.json({ balance: new URL(request.url).searchParams.get('user_id') === '8' ? '8.00' : '25.00', breakdown: {}, recent_transactions: [] })),
      http.get('*/api/payments/greenlight/overview/', async ({ request }) => {
        if (new URL(request.url).searchParams.get('user_id') === '7') {
          started = true;
          await delayed;
          return HttpResponse.json(overview({ balance_snapshot: { amount: '999.00', as_of: '2026-10-11T12:00:00Z' } }));
        }
        return HttpResponse.json(overview({ user_id: 8, balance_snapshot: null }));
      }),
    ] });
    await waitFor(() => expect(started).toBe(true), { timeout: 3000 });
    await user.selectOptions(screen.getByLabelText('Kid for payments and Greenlight'), '8');
    expect(await screen.findByText('$8.00')).toBeInTheDocument();
    await screen.findByRole('region', { name: /greenlight for beck/i });
    await act(async () => { release(); await delayed; });
    expect(screen.queryByText('$999.00')).not.toBeInTheDocument();
    expect(screen.queryByText('$25.00')).not.toBeInTheDocument();
  });

  it('discards a late CSV preview after switching children and scopes the next request to the new child', async () => {
    let release;
    const delayed = new Promise((resolve) => { release = resolve; });
    const previewCalls = [];
    const user = renderPage({ extra: [http.post('*/api/payments/greenlight/preview/', async ({ request }) => {
      previewCalls.push(await request.json());
      await delayed;
      return HttpResponse.json({ rows, schema: [] });
    })] });
    await user.click(await screen.findByLabelText('Or paste transfer CSV'));
    await user.paste(csv);
    await user.click(screen.getByRole('button', { name: /^preview csv$/i }));
    await waitFor(() => expect(previewCalls).toHaveLength(1));
    await user.selectOptions(screen.getByLabelText('Kid for payments and Greenlight'), '8');
    expect(await screen.findByLabelText('Or paste transfer CSV')).toHaveValue('');
    await act(async () => { release(); await delayed; });
    expect(screen.queryByLabelText('Action for row 2')).not.toBeInTheDocument();
    const next = spyHandler('post', /\/api\/payments\/greenlight\/preview\/$/, { rows: [], schema: [] });
    server.use(next.handler);
    await user.click(screen.getByLabelText('Or paste transfer CSV'));
    await user.paste(csv);
    await user.click(screen.getByRole('button', { name: /^preview csv$/i }));
    await waitFor(() => expect(next.calls).toHaveLength(1));
    expect(next.calls[0].body).toEqual({ user_id: 8, csv_data: csv });
  });

  it('refreshes the selected child balance and filtered ledger after a confirmed payout', async () => {
    let paid = false;
    const ledgerCalls = [];
    const balances = [];
    const payout = spyHandler('post', /\/api\/payments\/greenlight\/payout\/$/, () => {
      paid = true;
      return { created: true, payout: { id: 56 } };
    });
    const user = renderPage({ extra: [
      http.get('*/api/balance/', ({ request }) => {
        balances.push(new URL(request.url).searchParams.get('user_id'));
        return HttpResponse.json({ balance: paid ? '5.00' : '25.00', breakdown: {}, recent_transactions: [] });
      }),
      http.get('*/api/payments/', ({ request }) => {
        ledgerCalls.push(new URL(request.url).searchParams.get('user_id'));
        return HttpResponse.json(paid ? [{ id: 56, user: 7, entry_type: 'payout', amount: '-20.00', description: 'Confirmed payout', created_at: '2026-10-11T19:00:00Z' }] : []);
      }), payout.handler,
    ] });
    const dialog = await openTransfer(user);
    await user.click(dialog.getByRole('checkbox', { name: /already completed/i }));
    await user.click(dialog.getByRole('button', { name: /^record completed transfer$/i }));
    expect(await screen.findByText('Confirmed payout')).toBeInTheDocument();
    expect(await screen.findByText('$5.00')).toBeInTheDocument();
    expect(screen.getByText('$100.00')).toBeInTheDocument();
    expect(ledgerCalls).toEqual(['7', '7']);
    expect(balances).toEqual(['7', '7']);
  });

  it('clears an old account preview and parent controls when authentication changes', async () => {
    function ChangeAccount() {
      const { setUser } = useAuth();
      return <button onClick={() => setUser(buildUser({ id: 99, display_name: 'New child' }))}>Switch account</button>;
    }
    const preview = spyHandler('post', /\/api\/payments\/greenlight\/preview\/$/, { rows, schema: [] });
    const user = renderPage({ additional: <ChangeAccount />, extra: [preview.handler] });
    await user.click(await screen.findByLabelText('Or paste transfer CSV'));
    await user.paste(csv);
    await user.click(screen.getByRole('button', { name: /^preview csv$/i }));
    await screen.findByLabelText('Action for row 2');
    await user.click(screen.getByRole('button', { name: /switch account/i }));
    await screen.findByRole('region', { name: /greenlight for new child/i });
    expect(screen.queryByLabelText('Action for row 2')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /record completed transfer/i })).not.toBeInTheDocument();
  });
});
