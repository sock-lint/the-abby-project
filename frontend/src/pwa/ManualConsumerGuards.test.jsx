import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, renderWithProviders, screen, waitFor } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildParent } from '../test/factories';
import { PwaStatusProvider } from './PwaStatusProvider';
import { usePwaStatus } from './pwaStatus.context';
import GreenlightTransferForm from '../pages/payments/GreenlightTransferForm';
import GreenlightSnapshotForm from '../pages/payments/GreenlightSnapshotForm';
import GreenlightReconciliation from '../pages/payments/GreenlightReconciliation';
import JournalConversation from '../components/chronicle/JournalConversation';

vi.mock('./registerPromptWorker', () => ({ registerPromptWorker: () => ({ update: () => false, dispose: () => {} }) }));

function Protection() {
  const { updateBlocked } = usePwaStatus();
  return <output aria-label="Update protection">{updateBlocked ? 'Protected' : 'Ready'}</output>;
}

function mount(ui) {
  return renderWithProviders(<PwaStatusProvider><Protection />{ui}</PwaStatusProvider>);
}

async function protectedWork() {
  await waitFor(() => expect(screen.getByLabelText('Update protection')).toHaveTextContent('Protected'));
}

async function releasedWork() {
  await waitFor(() => expect(screen.getByLabelText('Update protection')).toHaveTextContent('Ready'));
}

beforeEach(() => {
  sessionStorage.clear();
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
});

describe('Manual consumer update guards', () => {
  it('keeps transfer details guarded after failure and releases only after a confirmed save', async () => {
    let attempts = 0;
    const payout = spyHandler('post', /\/api\/payments\/greenlight\/payout\/$/, () => ++attempts === 1
      ? HttpResponse.json({ error: 'Transfer save unavailable.' }, { status: 503 })
      : { created: true, payout: { id: 50 } });
    server.use(payout.handler);
    const onSaved = vi.fn();
    const { user } = mount(<GreenlightTransferForm userId={7} kidName="Alex" overview={{ approved_payable: '10.00' }} ownerKey="synthetic-parent-family-7" onClose={() => {}} onSaved={onSaved} />);
    await user.type(screen.getByLabelText('Transfer memo (optional)'), 'Completed outside Abby');
    await protectedWork();
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: 'Record completed transfer' }));
    await screen.findByText('Transfer save unavailable.');
    await protectedWork();
    expect(screen.getByLabelText('Transfer memo (optional)')).toHaveValue('Completed outside Abby');
    await user.click(screen.getByRole('button', { name: 'Retry recording this transfer' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    await releasedWork();
    expect(payout.calls[1].body).toEqual(payout.calls[0].body);
  });

  it('keeps an observed-balance draft guarded after validation failure and releases on confirmation', async () => {
    let attempts = 0;
    const snapshot = spyHandler('post', /\/api\/payments\/greenlight\/snapshot\/$/, () => ++attempts === 1
      ? HttpResponse.json({ amount: ['Check the observed amount.'] }, { status: 400 })
      : { id: 1, amount: '0.00' });
    server.use(snapshot.handler);
    const onSaved = vi.fn();
    const { user } = mount(<GreenlightSnapshotForm userId={7} kidName="Alex" onClose={() => {}} onSaved={onSaved} />);
    await user.type(screen.getByLabelText('Verified Greenlight balance'), '0');
    await user.type(screen.getByLabelText('Balance memo (optional)'), 'Checked today');
    await protectedWork();
    await user.click(screen.getByRole('button', { name: 'Save verified balance' }));
    await screen.findByText('Check the observed amount.');
    await protectedWork();
    await user.click(screen.getByRole('button', { name: 'Save verified balance' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    await releasedWork();
    expect(snapshot.calls[1].body).toEqual(snapshot.calls[0].body);
  });

  it('releases a conflicting transfer only after the parent reviews and discards the draft', async () => {
    server.use(http.post('*/api/payments/greenlight/payout/', () => HttpResponse.json({ error: 'Check the recorded transfer.' }, { status: 409 })));
    const { user } = mount(<GreenlightTransferForm userId={7} kidName="Alex" overview={{ approved_payable: '10.00' }} ownerKey="synthetic-parent-family-7" onClose={() => {}} onSaved={() => {}} />);
    await user.type(screen.getByLabelText('Greenlight reference (optional)'), 'transfer-123');
    await protectedWork();
    await user.click(screen.getByRole('checkbox', { name: /already completed/ }));
    await user.click(screen.getByRole('button', { name: 'Record completed transfer' }));
    await screen.findByText('Check the recorded transfer.');
    await protectedWork();
    const discard = screen.getByRole('button', { name: 'Discard conflicting transfer draft' });
    expect(discard).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /checked the recorded payouts/ }));
    await user.click(discard);
    await releasedWork();
    expect(screen.getByLabelText('Greenlight reference (optional)')).toHaveValue('');
    expect(sessionStorage.getItem('abby_greenlight_pending_transfer:synthetic-parent-family-7')).toBeNull();
    await user.type(screen.getByLabelText('Transfer amount'), '5');
    await protectedWork();
  });

  it('releases a balance observation when the parent restores its original fields', async () => {
    const { user } = mount(<GreenlightSnapshotForm userId={7} kidName="Alex" onClose={() => {}} onSaved={() => {}} />);
    await releasedWork();
    await user.type(screen.getByLabelText('Balance memo (optional)'), 'Unsaved observation');
    await protectedWork();
    await user.clear(screen.getByLabelText('Balance memo (optional)'));
    await releasedWork();
  });

  it('guards CSV choices through reconciliation failure and releases after the confirmed result clears them', async () => {
    const csv = 'date,amount,description,reference,type\n2026-10-11,10.00,Weekly earnings,transfer-1,transfer';
    const preview = spyHandler('post', /\/api\/payments\/greenlight\/preview\/$/, { rows: [
      { row_number: 2, fingerprint: 'first', date: '2026-10-11', amount: '10.00', description: 'Weekly earnings', eligible: true, duplicate: false, match_candidates: [] },
    ] });
    let attempts = 0;
    const reconcile = spyHandler('post', /\/api\/payments\/greenlight\/reconcile\/$/, () => ++attempts === 1
      ? HttpResponse.json({ error: 'Please check the current payouts.' }, { status: 409 })
      : { recorded: 1, matched: 0, duplicates: 0 });
    server.use(preview.handler, reconcile.handler);
    const { user } = mount(<GreenlightReconciliation userId={7} kidName="Alex" payouts={[]} timecards={[]} onSaved={() => {}} />);
    await user.click(screen.getByLabelText('Or paste transfer CSV'));
    await user.paste(csv);
    await protectedWork();
    await user.click(screen.getByRole('button', { name: 'Preview CSV' }));
    await user.selectOptions(await screen.findByLabelText('Action for row 2'), 'record');
    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: 'Reconcile 1 selected transfers' }));
    await screen.findByText('Please check the current payouts.');
    await protectedWork();
    expect(screen.getByLabelText('Action for row 2')).toHaveValue('record');
    await user.click(screen.getByRole('button', { name: 'Reconcile 1 selected transfers' }));
    await screen.findByText(/Reconciliation saved: 1 new payouts/);
    await releasedWork();
    expect(reconcile.calls[1].body).toEqual(reconcile.calls[0].body);
  });

  it('releases a CSV after clearing it without making a bookkeeping request', async () => {
    const preview = spyHandler('post', /\/api\/payments\/greenlight\/preview\/$/, { rows: [] });
    const reconcile = spyHandler('post', /\/api\/payments\/greenlight\/reconcile\/$/, { recorded: 0, matched: 0, duplicates: 0 });
    server.use(preview.handler, reconcile.handler);
    const { user } = mount(<GreenlightReconciliation userId={7} kidName="Alex" payouts={[]} timecards={[]} onSaved={() => {}} />);
    await user.type(screen.getByLabelText('Or paste transfer CSV'), 'A statement still being prepared');
    await protectedWork();
    await user.clear(screen.getByLabelText('Or paste transfer CSV'));
    await releasedWork();
    expect(preview.calls).toHaveLength(0);
    expect(reconcile.calls).toHaveLength(0);
  });

  it('guards an unfinished CSV file read and releases after a confirmed read failure', async () => {
    let failRead;
    const file = new File(['date,amount,description,reference,type'], 'transfers.csv', { type: 'text/csv' });
    Object.defineProperty(file, 'text', { value: () => new Promise((_, reject) => { failRead = reject; }) });
    const { user } = mount(<GreenlightReconciliation userId={7} kidName="Alex" payouts={[]} timecards={[]} onSaved={() => {}} />);
    await user.upload(screen.getByLabelText('Upload transfer CSV'), file);
    await protectedWork();
    await act(async () => failRead(new Error('File unavailable')));
    await screen.findByText('Could not read that file. Paste the CSV below instead.');
    await releasedWork();
  });

  it('protects a response when device draft storage fails and releases after the server confirms it', async () => {
    const realSet = Storage.prototype.setItem;
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (key, value) {
      if (key.startsWith('abby:journal-response:')) throw new Error('Storage unavailable');
      return realSet.call(this, key, value);
    });
    try {
      let attempts = 0;
      server.use(http.get('*/api/chronicle/entries/23/comments/', () => HttpResponse.json([])));
      const post = spyHandler('post', /\/api\/chronicle\/entries\/23\/comments\/$/, ({ body }) => ++attempts === 1
        ? HttpResponse.json({ body: ['Try sending this response again.'] }, { status: 400 })
        : { id: 9, entry: 23, author: 99, author_name: 'Parent', author_role: 'parent', body: body.body, created_at: '2026-10-14T12:00:00Z' });
      server.use(post.handler);
      const { user } = mount(<JournalConversation entry={{ id: 23, user: 1, kind: 'journal', is_private: false }} defaultOpen />);
      await user.type(await screen.findByRole('textbox'), 'Keep this response until it saves.');
      await protectedWork();
      await user.click(screen.getByRole('button', { name: 'Family responses' }));
      await protectedWork();
      await user.click(screen.getByRole('button', { name: 'Family responses' }));
      expect(await screen.findByRole('textbox')).toHaveValue('Keep this response until it saves.');
      await user.click(screen.getByRole('button', { name: 'Send response' }));
      await screen.findByText('Try sending this response again.');
      await protectedWork();
      await user.click(screen.getByRole('button', { name: 'Send response' }));
      await screen.findByText('Response saved with this memory.');
      await releasedWork();
      expect(post.calls[0].body.body).toBe(post.calls[1].body.body);
    } finally {
      storage.mockRestore();
    }
  });
});
