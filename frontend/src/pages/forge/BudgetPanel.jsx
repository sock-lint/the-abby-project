import { useState } from 'react';
import { Scale, SlidersHorizontal, Timer } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import ProgressBar from '../../components/ProgressBar';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import EmptyState from '../../components/EmptyState';
import { CheckboxField, TextField } from '../../components/form';
import { adjustPrintBudget, getPrintBudgetLedger, updatePrintBudget } from '../../api';
import { fieldErrors, normalizeList } from '../../utils/api';
import { formatDate } from '../../utils/format';
import {
  formatCap, formatGrams, formatMinutes, isOverage, usagePercent,
} from './forge.constants';

function Dimension({ icon, label, used, cap, remaining, unit, barLabel }) {
  const over = isOverage(remaining);
  const uncapped = cap === null || cap === undefined;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 font-rune text-micro uppercase tracking-wider text-ink-whisper">
          {icon} {label}
        </span>
        <span className={`font-body text-caption ${over ? 'text-ember-deep' : 'text-ink-secondary'}`}>
          {unit === 'minutes' ? formatMinutes(used) : formatGrams(used)}
          {' / '}
          {formatCap(cap, unit)}
        </span>
      </div>
      {!uncapped && (
        <ProgressBar
          value={usagePercent(used, cap)}
          color={over ? 'bg-ember' : 'bg-sheikah-teal-deep'}
          aria-label={barLabel}
        />
      )}
      {over && (
        <div className="font-script text-caption text-ember-deep">
          Over by {unit === 'minutes'
            ? formatMinutes(Math.abs(Number(remaining)))
            : formatGrams(Math.abs(Number(remaining)))}
        </div>
      )}
    </div>
  );
}

function BudgetRow({ budget, onChanged }) {
  const [pane, setPane] = useState(null); // null | 'caps' | 'adjust' | 'ledger'
  const [grams, setGrams] = useState(
    budget.grams_per_month === null || budget.grams_per_month === undefined
      ? '' : String(budget.grams_per_month),
  );
  const [minutes, setMinutes] = useState(
    budget.minutes_per_month === null || budget.minutes_per_month === undefined
      ? '' : String(budget.minutes_per_month),
  );
  const [active, setActive] = useState(budget.is_active !== false);
  const [requiresCoins, setRequiresCoins] = useState(budget.minutes_per_coin != null);
  const [minutesPerCoin, setMinutesPerCoin] = useState(String(budget.minutes_per_coin ?? 1));
  const [rateError, setRateError] = useState('');
  const [adjGrams, setAdjGrams] = useState('');
  const [adjMinutes, setAdjMinutes] = useState('');
  const [adjNote, setAdjNote] = useState('');
  const [ledger, setLedger] = useState(null);
  const [ledgerLoading, setLedgerLoading] = useState(false);
  const [ledgerError, setLedgerError] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  // Blank means "no cap on that dimension" — the backend stores null, and
  // null is genuinely different from 0 ("nothing this month").
  const capValue = (value) => {
    const trimmed = (value ?? '').toString().trim();
    if (trimmed === '') return null;
    const n = Number(trimmed);
    return Number.isNaN(n) ? null : n;
  };

  const loadLedger = async () => {
    if (ledgerLoading) return;
    setLedgerLoading(true);
    setLedgerError('');
    try {
      setLedger(normalizeList(await getPrintBudgetLedger(budget.id)));
    } catch (err) {
      setLedgerError(err?.message || 'Could not load the ledger.');
    } finally {
      setLedgerLoading(false);
    }
  };

  const togglePane = (next) => {
    setError('');
    const target = pane === next ? null : next;
    setPane(target);
    if (target === 'ledger' && ledger === null) {
      loadLedger();
    }
  };

  const saveCaps = async () => {
    const rate = Number(minutesPerCoin);
    if (requiresCoins && (!Number.isInteger(rate) || rate <= 0)) {
      setRateError('Enter a whole number of minutes greater than zero.');
      return;
    }
    setBusy(true);
    setError('');
    setRateError('');
    try {
      await updatePrintBudget(budget.id, {
        grams_per_month: capValue(grams),
        minutes_per_month: capValue(minutes),
        minutes_per_coin: requiresCoins ? rate : null,
        is_active: active,
      });
      setPane(null);
      onChanged?.();
    } catch (err) {
      const fields = fieldErrors(err);
      setRateError(fields.minutes_per_coin || '');
      if (!fields.minutes_per_coin) setError(err?.message || 'Could not save those caps.');
    } finally {
      setBusy(false);
    }
  };

  const saveAdjustment = async () => {
    setBusy(true);
    setError('');
    try {
      await adjustPrintBudget(budget.id, {
        grams: Number(adjGrams) || 0,
        minutes: Number(adjMinutes) || 0,
        note: adjNote.trim(),
      });
      setAdjGrams('');
      setAdjMinutes('');
      setAdjNote('');
      setLedger(null);
      setPane(null);
      onChanged?.();
    } catch (err) {
      setError(err?.message || 'Could not record that adjustment.');
    } finally {
      setBusy(false);
    }
  };

  const name = budget.user_name || budget.username || 'This child';

  return (
    <ParchmentCard className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="font-display text-base text-ink-primary leading-tight">{name}</div>
          {budget.is_active === false && (
            <div className="font-script text-caption text-ink-whisper">
              Caps are off — usage is still ledgered, never enforced.
            </div>
          )}
        </div>
        <div className="flex gap-1">
          <Button variant="ghost" size="sm" onClick={() => togglePane('caps')}>
            Caps
          </Button>
          <Button variant="ghost" size="sm" onClick={() => togglePane('adjust')}>
            Adjust
          </Button>
          <Button variant="ghost" size="sm" onClick={() => togglePane('ledger')}>
            Ledger
          </Button>
        </div>
      </div>

      <Dimension
        icon={<Scale size={12} aria-hidden="true" />}
        label="Filament"
        used={budget.grams_used}
        cap={budget.grams_per_month}
        remaining={budget.grams_remaining}
        unit="grams"
        barLabel={`${name} filament used this month`}
      />
      <Dimension
        icon={<Timer size={12} aria-hidden="true" />}
        label="Print time"
        used={budget.minutes_used}
        cap={budget.minutes_per_month}
        remaining={budget.minutes_remaining}
        unit="minutes"
        barLabel={`${name} print time used this month`}
      />

      <p className="font-body text-caption text-ink-secondary">
        {budget.minutes_per_coin != null
          ? `Coin exchange: 1 coin per ${budget.minutes_per_coin} print ${Number(budget.minutes_per_coin) === 1 ? 'minute' : 'minutes'}.`
          : 'Coin exchange is off. New approvals are free.'}
      </p>

      {error && <ErrorAlert message={error} />}

      {pane === 'caps' && (
        <div className="space-y-2 border-t border-ink-page-shadow/40 pt-3">
          <TextField
            id={`forge-cap-grams-${budget.id}`}
            label="Grams per month"
            type="number"
            min="0"
            value={grams}
            onChange={(e) => setGrams(e.target.value)}
            helpText="Leave blank for no cap."
          />
          <TextField
            id={`forge-cap-minutes-${budget.id}`}
            label="Minutes per month"
            type="number"
            min="0"
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
            helpText="Leave blank for no cap."
          />
          <CheckboxField
            id={`forge-cap-active-${budget.id}`}
            label="Enforce these caps"
            checked={active}
            onChange={(e) => setActive(e.target.checked)}
          />
          <CheckboxField
            id={`forge-coins-required-${budget.id}`}
            label="Require coins for new prints"
            checked={requiresCoins}
            onChange={(e) => { setRequiresCoins(e.target.checked); setRateError(''); }}
          />
          {requiresCoins && (
            <TextField
              id={`forge-minutes-per-coin-${budget.id}`}
              label="Print minutes per coin"
              type="number"
              min="1"
              step="1"
              value={minutesPerCoin}
              onChange={(e) => { setMinutesPerCoin(e.target.value); setRateError(''); }}
              error={rateError}
              helpText="The parent's time estimate is rounded up to whole coins. Existing quotes keep their saved price."
            />
          )}
          <p className="font-body text-caption text-ink-whisper">
            Children accept the fixed quote before printing. Retries do not cost extra coins.
            Cancelling before the first print job refunds exchanged coins.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setPane(null)}>Cancel</Button>
            <Button size="sm" onClick={saveCaps} loading={busy}>Save caps</Button>
          </div>
        </div>
      )}

      {pane === 'adjust' && (
        <div className="space-y-2 border-t border-ink-page-shadow/40 pt-3">
          <p className="font-script text-caption text-ink-whisper">
            Nothing is ever edited or deleted — a correction is its own entry.
            Positive consumes budget, negative gives it back.
          </p>
          {/* Signed fields — inputMode="text" keeps a minus-capable keyboard
              ("negative gives it back"; the iOS numeric pad has no minus). */}
          <TextField
            id={`forge-adj-grams-${budget.id}`}
            label="Grams"
            type="number"
            inputMode="text"
            value={adjGrams}
            onChange={(e) => setAdjGrams(e.target.value)}
          />
          <TextField
            id={`forge-adj-minutes-${budget.id}`}
            label="Minutes"
            type="number"
            inputMode="text"
            value={adjMinutes}
            onChange={(e) => setAdjMinutes(e.target.value)}
          />
          <TextField
            id={`forge-adj-note-${budget.id}`}
            label="Note"
            value={adjNote}
            onChange={(e) => setAdjNote(e.target.value.slice(0, 200))}
            placeholder="Spool ran out mid-print"
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setPane(null)}>Cancel</Button>
            <Button size="sm" onClick={saveAdjustment} loading={busy}>Record</Button>
          </div>
        </div>
      )}

      {pane === 'ledger' && (
        <div className="border-t border-ink-page-shadow/40 pt-3">
          {ledgerLoading ? (
            <div className="font-script text-caption text-ink-whisper">Loading…</div>
          ) : ledgerError ? (
            <ErrorAlert message={ledgerError} onRetry={loadLedger} />
          ) : ledger === null ? null : ledger.length === 0 ? (
            <div className="font-script text-caption text-ink-whisper">
              Nothing debited yet.
            </div>
          ) : (
            <ul className="space-y-1.5">
              {ledger.slice(0, 12).map((row) => (
                <li key={row.id} className="flex items-baseline justify-between gap-2">
                  <span className="min-w-0">
                    <span className="font-body text-caption text-ink-primary">
                      {row.reason_display || row.reason}
                    </span>
                    {row.request_title && (
                      <span className="font-script text-caption text-ink-whisper">
                        {' '}· {row.request_title}
                      </span>
                    )}
                    {row.note && (
                      <span className="font-script text-caption text-ink-whisper">
                        {' '}· {row.note}
                      </span>
                    )}
                  </span>
                  <span className="font-body text-caption text-ink-secondary shrink-0 tabular-nums">
                    {formatGrams(row.grams)} · {formatMinutes(row.minutes)}
                    <span className="text-ink-whisper"> · {formatDate(row.created_at)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </ParchmentCard>
  );
}

/**
 * BudgetPanel — parent-only. Per-child grams + minutes against the monthly
 * cap, the inline cap editor, the manual-adjustment form, and the recent
 * ledger.
 *
 * Two dimensions, independently capped, either of which may be null for
 * "no cap" — a household that only cares about filament leaves minutes
 * blank. Remaining is allowed to go negative and is shown in the ember tone
 * rather than clamped, because an overage is exactly the thing a parent
 * needs to see.
 */
export default function BudgetPanel({ budgets, onChanged }) {
  if (!budgets || budgets.length === 0) {
    return (
      <EmptyState icon={<SlidersHorizontal size={24} />}>
        No print budgets yet — they appear once a child is in the family.
      </EmptyState>
    );
  }
  return (
    <div className="space-y-3">
      {budgets.map((budget) => (
        <BudgetRow key={budget.id} budget={budget} onChanged={onChanged} />
      ))}
    </div>
  );
}
