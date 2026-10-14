import { useRef, useState } from 'react';
import { recordGreenlightPayout } from '../../api';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import { CheckboxField, DateField, SelectField, TextField, TextAreaField } from '../../components/form';
import { fieldErrors } from '../../utils/api';
import { toISODate } from '../../utils/dates';
import { formatCurrency, formatDate } from '../../utils/format';
import { readPendingTransfer, savePendingTransfer } from './greenlightDraft';
import { usePwaUpdateGuard } from '../../pwa/usePwaUpdateGuard';

export default function GreenlightTransferForm({ userId, kidName, overview, ownerKey, onClose, onSaved }) {
  const [pending] = useState(() => readPendingTransfer(ownerKey, userId));
  const [form, setForm] = useState(() => pending?.payload ? {
    ...pending.payload, timecard_id: pending.payload.timecard_id || '',
  } : {
    amount: Number(overview.approved_payable) > 0 ? overview.approved_payable : '',
    transferred_on: toISODate(new Date()), reference: '', memo: '', timecard_id: '',
  });
  const [confirmed, setConfirmed] = useState(!!pending);
  const [requestKey, setRequestKey] = useState(() => pending?.payload.idempotency_key || crypto.randomUUID());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [errors, setErrors] = useState({});
  const [retryPayload, setRetryPayload] = useState(pending?.payload || null);
  const [conflict, setConflict] = useState(pending?.conflict || false);
  const [reviewedConflict, setReviewedConflict] = useState(false);
  const saved = useRef({ form, confirmed });
  const dirty = JSON.stringify(form) !== JSON.stringify(saved.current.form) || confirmed !== saved.current.confirmed;
  usePwaUpdateGuard(dirty || saving);
  const cards = overview.approved_timecards || [];
  const edit = (changes) => {
    if (retryPayload) return;
    setForm((previous) => ({ ...previous, ...changes }));
    setRequestKey(crypto.randomUUID());
    setError('');
    setErrors({});
  };
  const discardReviewedConflict = () => {
    if (!conflict || !reviewedConflict || saving) return;
    savePendingTransfer(ownerKey, null);
    setRetryPayload(null);
    setConflict(false);
    setReviewedConflict(false);
    setRequestKey(crypto.randomUUID());
    const cleared = { amount: '', transferred_on: toISODate(new Date()), reference: '', memo: '', timecard_id: '' };
    saved.current = { form: cleared, confirmed: false };
    setForm(cleared);
    setConfirmed(false);
    setError('');
    setErrors({});
  };
  const submit = async (event) => {
    event.preventDefault();
    if (saving || !confirmed || conflict) return;
    setSaving(true);
    setError('');
    setErrors({});
    const payload = retryPayload || {
        user_id: Number(userId), amount: form.amount, transferred_on: form.transferred_on,
        reference: form.reference, memo: form.memo, idempotency_key: requestKey,
        timecard_id: form.timecard_id ? Number(form.timecard_id) : null,
    };
    savePendingTransfer(ownerKey, { payload, conflict: false });
    try {
      await recordGreenlightPayout(payload);
      savePendingTransfer(ownerKey, null);
      saved.current = { form, confirmed };
      onSaved();
    } catch (failure) {
      const fields = fieldErrors(failure);
      setErrors(fields);
      setError(Object.keys(fields).length ? 'Check the transfer details below.' : failure.message);
      // A disconnected/failed response may follow a committed ledger write.
      // Freeze its identity and exact payload until the server confirms it.
      if (failure.status === undefined || failure.status >= 500 || failure.status === 408 || failure.status === 409) {
        setRetryPayload(payload);
        savePendingTransfer(ownerKey, { payload, conflict: failure.status === 409 });
      } else {
        savePendingTransfer(ownerKey, null);
      }
      if (failure.status === 409) setConflict(true);
      if (failure.status === 400) setRetryPayload(null);
    } finally {
      setSaving(false);
    }
  };
  return (
    <BottomSheet title={`Record a Greenlight transfer for ${kidName}`} onClose={onClose} disabled={saving}>
      <p className="text-body text-ink-secondary mb-3">
        Send the money in Greenlight first, then record the completed transfer here. Recording it reduces what you owe {kidName}.
      </p>
      <ErrorAlert message={error} />
      {retryPayload && <p role="status" className="text-body text-ink-secondary mb-3">
        {conflict ? 'This transfer conflicts with an existing record. Check the recorded payouts before starting another transfer record.' : 'The save was not confirmed. These details are locked so retrying can confirm the same transfer safely.'}
      </p>}
      {conflict && <div className="space-y-3 mb-3">
        <CheckboxField label="I checked the recorded payouts and need to record a different completed transfer"
          checked={reviewedConflict} onChange={(event) => setReviewedConflict(event.target.checked)} />
        <Button variant="secondary" onClick={discardReviewedConflict} disabled={!reviewedConflict || saving}>
          Discard conflicting transfer draft
        </Button>
      </div>}
      <form onSubmit={submit} className="space-y-3">
        <fieldset disabled={saving || !!retryPayload} className="space-y-3">
          <SelectField label="Approved timecard (optional)" value={form.timecard_id} error={errors.timecard_id}
            onChange={(event) => {
              const card = cards.find((item) => String(item.id) === event.target.value);
              edit({ timecard_id: event.target.value, amount: card ? card.total_earnings : '' });
            }} helpText="Choosing a timecard records its full payout and marks it paid.">
            <option value="">General earnings — no timecard</option>
            {cards.map((card) => <option key={card.id} value={card.id}>Week of {formatDate(card.week_start)} · {formatCurrency(card.total_earnings)}</option>)}
          </SelectField>
          <TextField label="Transfer amount" type="number" step="0.01" min="0.01" required
            readOnly={!!form.timecard_id} value={form.amount} error={errors.amount}
            onChange={(event) => edit({ amount: event.target.value })} />
          <DateField label="Transferred on" required value={form.transferred_on} error={errors.transferred_on}
            onChange={(event) => edit({ transferred_on: event.target.value })} />
          <TextField label="Greenlight reference (optional)" value={form.reference} error={errors.reference} maxLength={200}
            onChange={(event) => edit({ reference: event.target.value })} />
          <TextAreaField label="Transfer memo (optional)" value={form.memo} error={errors.memo} maxLength={1000}
            onChange={(event) => edit({ memo: event.target.value })} />
          <CheckboxField label="I already completed this earned-money transfer in Greenlight" checked={confirmed}
            onChange={(event) => setConfirmed(event.target.checked)} />
        </fieldset>
        <div className="flex justify-end gap-2 flex-wrap">
          <Button variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="submit" disabled={saving || !confirmed || conflict}>{saving ? 'Recording…' : retryPayload ? 'Retry recording this transfer' : 'Record completed transfer'}</Button>
        </div>
      </form>
    </BottomSheet>
  );
}
