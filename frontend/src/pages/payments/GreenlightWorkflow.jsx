import { useEffect, useRef, useState } from 'react';
import { getGreenlightOverview } from '../../api';
import { getToken } from '../../api/client';
import { useApi } from '../../hooks/useApi';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import Loader from '../../components/Loader';
import ParchmentCard from '../../components/journal/ParchmentCard';
import SectionHeader from '../../components/SectionHeader';
import { formatCurrency, formatDate, formatDateTime } from '../../utils/format';
import GreenlightTransferForm from './GreenlightTransferForm';
import GreenlightSnapshotForm from './GreenlightSnapshotForm';
import GreenlightReconciliation from './GreenlightReconciliation';

// The owning page keys this subtree by account and child. Both drafts and
// async results belong to that identity and disappear on a selection change.
export default function GreenlightWorkflow({ userId, kidName, isParent, ownerKey, onLedgerChanged }) {
  const { data: overview, loading, refreshing, error, reload } = useApi(
    (signal) => getGreenlightOverview(userId, signal), [userId],
  );
  const [sheet, setSheet] = useState(null);
  const [notice, setNotice] = useState('');
  const active = useRef(true);
  const credential = useRef(getToken());
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);
  const saved = (message, ledgerChanged) => {
    if (!active.current || getToken() !== credential.current) return;
    setSheet(null);
    setNotice(message);
    reload();
    if (ledgerChanged) onLedgerChanged();
  };

  return (
    <section aria-label={`Greenlight for ${kidName}`} className="space-y-3">
      <SectionHeader title="Greenlight" kicker={kidName} />
      {loading ? <Loader /> : error || !overview ? <div className="space-y-2">
        <ErrorAlert message={error || 'Could not load Greenlight records.'} />
        <Button variant="secondary" onClick={reload}>Retry Greenlight records</Button>
      </div> : <>
        {notice && <p role="status" className="text-body text-moss">{notice}</p>}
        {refreshing && <p role="status" className="text-caption text-ink-secondary">Updating Greenlight records…</p>}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <ParchmentCard className="space-y-2">
            <h3 className="font-display text-xl text-ink-primary">Earnings ready to pay</h3>
            <p className="font-display text-3xl text-moss tabular-nums">{formatCurrency(overview.approved_payable)}</p>
            <p className="text-body text-ink-secondary">{formatCurrency(overview.pending_hourly)} in hourly earnings awaiting approval.</p>
            {isParent && <Button onClick={() => setSheet('transfer')} disabled={refreshing}>Record completed transfer</Button>}
          </ParchmentCard>
          <ParchmentCard className="space-y-2">
            <h3 className="font-display text-xl text-ink-primary">Last parent-verified Greenlight balance</h3>
            {overview.balance_snapshot ? <>
              <p className="font-display text-3xl text-sheikah-teal-deep tabular-nums">{formatCurrency(overview.balance_snapshot.amount)}</p>
              <p className="text-body text-ink-secondary">As of {formatDateTime(overview.balance_snapshot.as_of)}</p>
              {overview.balance_snapshot.memo && <p className="text-caption text-ink-secondary break-words">{overview.balance_snapshot.memo}</p>}
            </> : <p className="text-body text-ink-secondary">Unknown — no Greenlight balance has been verified yet.</p>}
            <p className="text-caption text-ink-secondary">This is a saved observation, separate from money still owed. Transfers and statement imports do not update it.</p>
            {isParent && <Button variant="secondary" onClick={() => setSheet('snapshot')} disabled={refreshing}>Verify Greenlight balance</Button>}
          </ParchmentCard>
        </div>
        <p className="text-body text-ink-secondary">Complete transfers in Greenlight. This page records them; it does not move money or fetch a live Greenlight balance.</p>
        {(overview.payouts || []).length > 0 && <ParchmentCard className="space-y-3">
          <h3 className="font-display text-xl text-ink-primary">Recorded payouts</h3>
          <ul className="space-y-3">
            {overview.payouts.map((payout) => <li key={payout.id} className="flex justify-between gap-3 flex-wrap text-body">
              <div className="min-w-0">
                <p className="text-ink-primary break-words">{payout.memo || payout.reference || `Payout #${payout.id}`}</p>
                <p className="text-caption text-ink-secondary">{payout.transferred_on ? `Transferred on ${formatDate(payout.transferred_on)}` : `Recorded on ${formatDate(payout.created_at)} · transfer date unknown`} · {payout.reconciled ? 'Matched to statement' : 'Not yet reconciled'}</p>
              </div>
              <span className="font-semibold text-ink-primary tabular-nums">{formatCurrency(payout.amount)}</span>
            </li>)}
          </ul>
        </ParchmentCard>}
        {isParent && <GreenlightReconciliation userId={userId} kidName={kidName} payouts={overview.payouts || []} timecards={overview.approved_timecards || []}
          onSaved={() => saved('Selected Greenlight transfers reconciled.', true)} />}
        {isParent && sheet === 'transfer' && <GreenlightTransferForm userId={userId} kidName={kidName} overview={overview} ownerKey={ownerKey}
          onClose={() => setSheet(null)} onSaved={() => saved('Completed transfer recorded.', true)} />}
        {isParent && sheet === 'snapshot' && <GreenlightSnapshotForm userId={userId} kidName={kidName}
          onClose={() => setSheet(null)} onSaved={() => saved('Greenlight balance snapshot saved.', false)} />}
      </>}
    </section>
  );
}
