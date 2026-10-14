import { useEffect, useRef, useState } from 'react';
import { previewGreenlightCsv, reconcileGreenlightCsv } from '../../api';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { CheckboxField, SelectField, TextAreaField, TextField } from '../../components/form';
import { formatCurrency, formatDate } from '../../utils/format';
import { fieldErrors } from '../../utils/api';
import { usePwaUpdateGuard } from '../../pwa/usePwaUpdateGuard';

export default function GreenlightReconciliation({ userId, kidName, payouts, timecards, onSaved }) {
  const [csv, setCsv] = useState('');
  const [preview, setPreview] = useState(null);
  const [choices, setChoices] = useState({});
  const [cardChoices, setCardChoices] = useState({});
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [readingFile, setReadingFile] = useState(false);
  const [error, setError] = useState('');
  const [csvError, setCsvError] = useState('');
  const [result, setResult] = useState(null);
  const active = useRef(true);
  const fileVersion = useRef(0);
  const hasChoices = Object.values(choices).some((value) => value && value !== 'ignore')
    || Object.values(cardChoices).some(Boolean);
  usePwaUpdateGuard(busy || readingFile || Boolean(csv) || hasChoices || confirmed);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);

  const updateCsv = (value) => {
    fileVersion.current += 1;
    setReadingFile(false);
    setCsv(value);
    setPreview(null);
    setChoices({});
    setCardChoices({});
    setConfirmed(false);
    setResult(null);
    setError('');
    setCsvError('');
  };
  const upload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 512 * 1024) {
      setCsvError('Choose a CSV no larger than 512 KB.');
      return;
    }
    updateCsv('');
    const version = ++fileVersion.current;
    setReadingFile(true);
    try {
      const value = await file.text();
      if (active.current && fileVersion.current === version) updateCsv(value);
    } catch {
      if (active.current && fileVersion.current === version) setCsvError('Could not read that file. Paste the CSV below instead.');
    } finally {
      if (active.current && fileVersion.current === version) setReadingFile(false);
    }
  };
  const loadPreview = async (event) => {
    event.preventDefault();
    if (busy || !csv.trim()) return;
    setBusy(true);
    setError('');
    setCsvError('');
    setResult(null);
    // Keep exactly the bytes previewed for stateless server reconciliation.
    const source = csv;
    const version = fileVersion.current;
    try {
      const response = await previewGreenlightCsv({ user_id: Number(userId), csv_data: source });
      if (!active.current || fileVersion.current !== version) return;
      if (!Array.isArray(response.rows)) throw new Error('Could not read the CSV preview. Try again.');
      setPreview({ ...response, source });
      setChoices({});
      setCardChoices({});
      setConfirmed(false);
    } catch (failure) {
      if (!active.current || fileVersion.current !== version) return;
      const fields = fieldErrors(failure);
      setCsvError(fields.csv_data || '');
      setError(fields.csv_data ? '' : failure.message);
    } finally {
      if (active.current) setBusy(false);
    }
  };
  const selections = (preview?.rows || [])
    .filter((row) => row.eligible && !row.duplicate && choices[row.fingerprint] && choices[row.fingerprint] !== 'ignore')
    .map((row) => ({
      fingerprint: row.fingerprint,
      match_payment_id: choices[row.fingerprint] === 'record' ? null : Number(choices[row.fingerprint]),
      timecard_id: choices[row.fingerprint] === 'record' && cardChoices[row.fingerprint] ? Number(cardChoices[row.fingerprint]) : null,
    }));
  const reconcile = async () => {
    if (busy || !confirmed || selections.length === 0) return;
    setBusy(true);
    setError('');
    try {
      const response = await reconcileGreenlightCsv({
        user_id: Number(userId), csv_data: preview.source, selections,
      });
      if (!active.current) return;
      setResult(response);
      setPreview(null);
      setCsv('');
      setChoices({});
      setCardChoices({});
      setConfirmed(false);
      onSaved();
    } catch (failure) {
      if (!active.current) return;
      const fields = fieldErrors(failure);
      setError(fields.selections || fields.csv_data || failure.message);
    } finally {
      if (active.current) setBusy(false);
    }
  };
  return (
    <ParchmentCard className="space-y-3">
      <h3 className="font-display text-xl text-ink-primary">Reconcile Greenlight transfers</h3>
      <p className="text-body text-ink-secondary">
        Preview a CSV and choose only transfers that paid {kidName} for earned money. Match a transfer you already recorded to avoid subtracting it twice. Purchases, allowance, gifts and unrelated credits should be ignored.
      </p>
      <p className="text-caption text-ink-secondary break-words">
        CSV columns: <code>date,amount,description,reference,type</code>. Use YYYY-MM-DD dates, positive dollar amounts, and <code>transfer</code> as the type for payout candidates. Other types are ignored. Adapt an exported statement to these columns before uploading.
      </p>
      <ErrorAlert message={error} />
      {result && <p role="status" className="text-body text-moss">Reconciliation saved: {result.recorded} new payouts, {result.matched} matched transfers, {result.duplicates} already reconciled.</p>}
      <form onSubmit={loadPreview} className="space-y-3">
        <TextField label="Upload transfer CSV" type="file" accept=".csv,text/csv" disabled={busy} onChange={upload} />
        <TextAreaField label="Or paste transfer CSV" rows={4} value={csv} disabled={busy} error={csvError}
          onChange={(event) => updateCsv(event.target.value)} placeholder={'date,amount,description,reference,type\n2026-10-11,10.00,Weekly earnings,transfer-123,transfer'} />
        <Button type="submit" variant="secondary" disabled={busy || !csv.trim()}>{busy ? 'Working…' : 'Preview CSV'}</Button>
      </form>
      {preview && (
        <div className="space-y-3">
          <p role="status" className="text-body text-ink-secondary">{preview.rows.length} statement rows. Each row starts ignored; choose the earned-money transfers to reconcile.</p>
          {preview.rows.map((row) => (
            <div key={`${row.row_number}-${row.fingerprint}`} className="rounded-xl border border-ink-page-shadow p-3 space-y-2">
              <div className="flex justify-between items-start gap-3 flex-wrap">
                <div className="min-w-0">
                  <p className="text-body text-ink-primary break-words">Row {row.row_number}: {row.description || 'Untitled transaction'}</p>
                  <p className="text-caption text-ink-secondary">{formatDate(row.date)}{row.reference ? ` · ${row.reference}` : ''}</p>
                </div>
                <span className="font-semibold tabular-nums text-ink-primary">{formatCurrency(row.amount)}</span>
              </div>
              {row.duplicate ? <p className="text-caption text-moss">Duplicate statement row or already reconciled — no additional payout will be recorded for this row.</p>
                : !row.eligible ? <p className="text-caption text-ink-secondary">Ignored: {row.error || 'This is not an eligible payout transfer.'}</p>
                  : <SelectField label={`Action for row ${row.row_number}`} disabled={busy} value={choices[row.fingerprint] || 'ignore'}
                    onChange={(event) => {
                      setChoices((previous) => ({ ...previous, [row.fingerprint]: event.target.value }));
                      setCardChoices((previous) => ({ ...previous, [row.fingerprint]: '' }));
                      setConfirmed(false);
                    }}>
                    <option value="ignore">Ignore this transaction</option>
                    <option value="record">Record a new earned-money payout</option>
                    {(row.match_candidates || []).map((id) => {
                      const payout = payouts.find((item) => item.id === id);
                      return <option key={id} value={id}>Match recorded payout #{id}{payout ? ` · ${formatCurrency(payout.amount)} · ${payout.transferred_on ? `transferred ${formatDate(payout.transferred_on)}` : `recorded ${formatDate(payout.created_at)}`}` : ''}</option>;
                    })}
                  </SelectField>}
              {choices[row.fingerprint] === 'record' && timecards.some((card) => Number(card.total_earnings) === Number(row.amount)) &&
                <SelectField label={`Timecard for row ${row.row_number} (optional)`} value={cardChoices[row.fingerprint] || ''} disabled={busy}
                  helpText="Choose the approved timecard this full transfer paid to mark that week paid."
                  onChange={(event) => {
                    setCardChoices((previous) => ({ ...previous, [row.fingerprint]: event.target.value }));
                    setConfirmed(false);
                  }}>
                  <option value="">General earnings — no timecard</option>
                  {timecards.filter((card) => Number(card.total_earnings) === Number(row.amount)).map((card) => <option key={card.id} value={card.id}>Week of {formatDate(card.week_start)} · {formatCurrency(card.total_earnings)}</option>)}
                </SelectField>}
            </div>
          ))}
          {selections.length > 0 && <CheckboxField label={`These ${selections.length} selected transfers paid ${kidName} for earned money`}
            checked={confirmed} disabled={busy} onChange={(event) => setConfirmed(event.target.checked)} />}
          <Button onClick={reconcile} disabled={busy || !confirmed || selections.length === 0}>
            {busy ? 'Reconciling…' : `Reconcile ${selections.length} selected transfers`}
          </Button>
        </div>
      )}
    </ParchmentCard>
  );
}
