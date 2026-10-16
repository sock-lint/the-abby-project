import { useCallback, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Box, Plus } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import {
  cancelPrintRequest,
  exchangePrintRequest,
  listPrintBudgets,
  listPrintRequests,
  listPrinters,
} from '../../api';
import { normalizeList } from '../../utils/api';
import Loader from '../../components/Loader';
import EmptyState from '../../components/EmptyState';
import ErrorAlert from '../../components/ErrorAlert';
import Button from '../../components/Button';
import ConfirmDialog from '../../components/ConfirmDialog';
import ChapterRubric from '../../components/atlas/ChapterRubric';
import PageHeader from '../../components/layout/PageHeader';
import PrintRequestCard from './PrintRequestCard';
import PrintRequestModal from './PrintRequestModal';
import ApprovalSheet from './ApprovalSheet';
import usePrintRequestRefresh from './usePrintRequestRefresh';
import {
  CLOSED_REQUEST_STATUSES, OPEN_REQUEST_STATUSES,
} from './forge.constants';

/** Shared request and fulfillment view in Rewards. Printer administration lives
 * in Manage; project parts use this same request and coin-exchange lifecycle. */
export default function Forge() {
  const { user, isParent } = useRole();
  const [searchParams] = useSearchParams();
  const [submitOpen, setSubmitOpen] = useState(searchParams.get('new') === '1');
  const [deciding, setDeciding] = useState(null);
  const [pendingCancel, setPendingCancel] = useState(null);
  const [actionError, setActionError] = useState('');
  const [busy, setBusy] = useState(false);
  const [exchanging, setExchanging] = useState(null);

  // Two fetches, not one, and the reason matters: the list endpoint is
  // paginated at PAGE_SIZE 20 and ordered newest-first. Deriving the approval
  // queue from a single unfiltered page means that once a family accumulates
  // 20 finished requests, a still-pending one falls off the end and silently
  // disappears from the parent's queue. Asking the server for the open
  // statuses keeps the actionable set whole no matter how much history piles
  // up behind it.
  const fetchOpen = useCallback(
    () => listPrintRequests({ status: OPEN_REQUEST_STATUSES.join(',') }), [],
  );
  const { data: openData, loading, error, reload: reloadOpen, setData: setOpenData } = useApi(fetchOpen);

  const fetchClosed = useCallback(
    () => listPrintRequests({ status: CLOSED_REQUEST_STATUSES.join(',') }), [],
  );
  const { data: closedData, reload: reloadClosed, setData: setClosedData } = useApi(fetchClosed);

  const reload = useCallback(() => {
    return Promise.all([reloadOpen(), reloadClosed()]);
  }, [reloadOpen, reloadClosed]);

  const fetchBudgets = useCallback(() => listPrintBudgets(), []);
  const {
    data: budgetsData, loading: budgetsLoading, error: budgetsError, reload: reloadBudgets,
  } = useApi(fetchBudgets);

  const fetchPrinters = useCallback(() => listPrinters(), []);
  const { data: printersData } = useApi(fetchPrinters);

  const open = useMemo(() => normalizeList(openData), [openData]);
  const closed = useMemo(() => normalizeList(closedData), [closedData]);
  // Saved mutation receipts update either list without inventing payment state.
  const requests = useMemo(() => [...open, ...closed], [open, closed]);
  // The server's own count, so a truncated history reads as "20 of 57"
  // rather than looking like the whole story.
  const closedTotal = closedData?.count ?? closed.length;
  const budgets = useMemo(() => normalizeList(budgetsData), [budgetsData]);
  const printers = useMemo(() => normalizeList(printersData), [printersData]);

  const pending = open.filter((r) => r.status === 'pending');
  const quotedCount = open.filter((r) => r.status === 'quoted').length;
  usePrintRequestRefresh({
    requests: open,
    reload,
    paused: submitOpen || Boolean(deciding) || busy || exchanging !== null
      || Boolean(searchParams.get('tab') && searchParams.get('tab') !== 'forge'),
  });

  const canCancel = (request) => (
    (isParent || request.user === user?.id)
    && ['pending', 'quoted', 'approved'].includes(request.status)
  );

  // Apply only the server's mutation receipt. Keeping it in the loaded lists
  // means a failed follow-up read cannot turn a paid print back into a quote.
  const applyReceipt = (saved) => {
    const confirmed = { ...requests.find((row) => row.id === saved.id), ...saved };
    const update = (data, statuses) => {
      const rows = normalizeList(data);
      const hadRow = rows.some((row) => row.id === confirmed.id);
      const include = statuses.includes(confirmed.status);
      const results = rows.filter((row) => row.id !== confirmed.id);
      if (include) results.unshift(confirmed);
      return Array.isArray(data) || !data ? results : {
        ...data, results, count: (data.count ?? rows.length) + Number(include) - Number(hadRow),
      };
    };
    setOpenData((data) => update(data, OPEN_REQUEST_STATUSES));
    setClosedData((data) => update(data, CLOSED_REQUEST_STATUSES));
  };

  const doExchange = async (request) => {
    if (exchanging !== null) return;
    setExchanging(request.id);
    setActionError('');
    try {
      const saved = await exchangePrintRequest(request.id);
      applyReceipt(saved);
      reload();
      reloadBudgets();
    } catch (err) {
      setActionError(err?.message || 'Could not exchange coins. Please try again.');
    } finally {
      setExchanging(null);
    }
  };

  const doCancel = async () => {
    if (!pendingCancel) return;
    setBusy(true);
    setActionError('');
    try {
      const saved = await cancelPrintRequest(pendingCancel.id);
      applyReceipt(saved);
      setPendingCancel(null);
      reload();
    } catch (err) {
      setActionError(err?.message || 'Could not cancel that request.');
    } finally {
      setBusy(false);
    }
  };

  const afterDecision = (saved) => {
    applyReceipt(saved);
    reload();
    reloadBudgets();
  };

  if (loading) return <Loader />;

  let rubricIndex = 0;
  const nextRubric = () => rubricIndex++;

  return (
    <div className="space-y-6">
      <PageHeader
        title="3D Prints"
        kicker="Rewards and parts for your projects"
        actions={isParent ? (
          <Link to="/manage?tab=3D+Printing" className="inline-flex min-h-11 items-center font-semibold text-sheikah-teal-deep underline">
            Printing settings
          </Link>
        ) : (
          <Button size="sm" onClick={() => setSubmitOpen(true)} className="flex items-center gap-1">
            <Plus size={16} aria-hidden="true" /> Ask for a print
          </Button>
        )}
      />
      <p className="font-body text-body text-ink-secondary">
        Choose something you want or a part for your project. A parent reviews each
        request and can approve it for free or send a coin quote for you to accept.
      </p>
      <ErrorAlert message={error || actionError} onRetry={error ? reload : undefined} />
      {budgetsError && <ErrorAlert message={`Could not load print budgets. ${budgetsError}`} onRetry={reloadBudgets} />}
      <div className="space-y-5">
        {isParent && pending.length > 0 && (
          <section>
            <ChapterRubric index={nextRubric()} name="Awaiting approval" />
            <div className="space-y-2">
              {pending.map((request) => (
                <PrintRequestCard
                  key={request.id}
                  request={request}
                  showOwner
                  showPlateFilename
                  canDecide
                  canCancel={canCancel(request)}
                  onDecide={setDeciding}
                  onCancel={setPendingCancel}
                />
              ))}
            </div>
          </section>
        )}

        <section>
          <ChapterRubric index={nextRubric()} name="Print requests" />
          {quotedCount > 0 && (
            <p className="font-body text-caption text-ink-secondary">
              {quotedCount} {quotedCount === 1 ? 'request awaits' : 'requests await'} coin exchange.
            </p>
          )}
          {open.length === 0 ? (
            <EmptyState icon={<Box size={28} />}>
              {isParent
                ? 'No open print requests right now.'
                : 'No print requests yet. Find a model you like and request a print.'}
            </EmptyState>
          ) : (
            <div className="space-y-2">
              {open
                .filter((r) => !(isParent && r.status === 'pending'))
                .map((request) => (
                  <PrintRequestCard
                    key={request.id}
                    request={request}
                    showOwner={isParent}
                    showPlateFilename={isParent}
                    canDecide={isParent && request.status === 'pending'}
                    canCancel={canCancel(request)}
                    canExchange={!isParent && request.user === user?.id && request.status === 'quoted'}
                    exchanging={exchanging === request.id}
                    exchangeDisabled={exchanging !== null}
                    onDecide={setDeciding}
                    onCancel={setPendingCancel}
                    onExchange={doExchange}
                  />
                ))}
            </div>
          )}
        </section>

        {closed.length > 0 && (
          <section>
            <ChapterRubric index={nextRubric()} name="Finished & closed" />
            {closedTotal > closed.length && (
              <p className="font-script text-caption text-ink-whisper mb-2">
                Showing the {closed.length} most recent of {closedTotal}.
              </p>
            )}
            <div className="space-y-2">
              {closed.map((request) => (
                <PrintRequestCard
                  key={request.id}
                  request={request}
                  showOwner={isParent}
                  showPlateFilename={isParent}
                />
              ))}
            </div>
          </section>
        )}
      </div>

      {submitOpen && !isParent && (
        <PrintRequestModal
          onClose={() => setSubmitOpen(false)}
          onSaved={() => { setSubmitOpen(false); reload(); }}
          printers={printers}
          budget={budgets.find((budget) => budget.user === user?.id)}
        />
      )}

      {deciding && (
        <ApprovalSheet
          request={deciding}
          budget={budgets.find((budget) => budget.user === deciding.user)}
          pricingLoading={budgetsLoading}
          pricingError={budgetsError}
          onClose={() => setDeciding(null)}
          onDecided={afterDecision}
        />
      )}

      {pendingCancel && (
        <ConfirmDialog
          title="Cancel this print request?"
          message={`“${pendingCancel.title}” will be cancelled. ${Number(pendingCancel.coins_paid) > 0
            ? 'Exchanged coins are refunded only if no print job has started.'
            : 'They can always ask again.'}`}
          confirmLabel={busy ? 'Cancelling…' : 'Cancel it'}
          onConfirm={doCancel}
          onCancel={() => setPendingCancel(null)}
        />
      )}
    </div>
  );
}
