import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Box, Plus } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import {
  cancelPrintRequest,
  listPrintBudgets,
  listPrintJobs,
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
import QuestFolio from '../quests/QuestFolio';
import PrintRequestCard from './PrintRequestCard';
import PrintRequestModal from './PrintRequestModal';
import ApprovalSheet from './ApprovalSheet';
import BudgetPanel from './BudgetPanel';
import PrinterStatus from './PrinterStatus';
import PrinterConfigPanel from './PrinterConfigPanel';
import UnlinkedJobsPanel from './UnlinkedJobsPanel';
import {
  CLOSED_REQUEST_STATUSES, OPEN_REQUEST_STATUSES, budgetProgress,
} from './forge.constants';

/**
 * Forge — the 3D print request tab of the Quests hub.
 *
 * The loop, in one paragraph: a child submits a link (or an uploaded model)
 * with a colour and a reason; a parent approves it, which attaches a monthly
 * filament + print-time budget and mints a plate filename; the parent slices
 * in Bambu Studio and saves the plate under exactly that name; our single
 * MQTT listener sees the printer start it, matches `subtask_name` to the
 * minted slug by exact equality, and streams progress back here until the
 * print finishes and the budget is debited.
 *
 * Role gating: children see their own requests, a submit button, and the
 * live printer view while one of their prints is running. Parents also get
 * the approval queue, the budget panel, the unlinked-jobs escape hatch, and
 * printer config.
 *
 * This is a hub tab, so it deliberately does NOT use PageShell — QuestFolio
 * is the shell every Quests tab wears, and the hub owns the page header.
 */
export default function Forge() {
  const { user, isParent } = useRole();
  const [searchParams] = useSearchParams();
  const [submitOpen, setSubmitOpen] = useState(searchParams.get('new') === '1');
  const [deciding, setDeciding] = useState(null);
  const [pendingCancel, setPendingCancel] = useState(null);
  const [actionError, setActionError] = useState('');
  const [busy, setBusy] = useState(false);

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
  const { data: openData, loading, error, reload: reloadOpen } = useApi(fetchOpen);

  const fetchClosed = useCallback(
    () => listPrintRequests({ status: CLOSED_REQUEST_STATUSES.join(',') }), [],
  );
  const { data: closedData, reload: reloadClosed } = useApi(fetchClosed);

  const reload = useCallback(() => {
    reloadOpen();
    reloadClosed();
  }, [reloadOpen, reloadClosed]);

  const fetchBudgets = useCallback(() => listPrintBudgets(), []);
  const { data: budgetsData, reload: reloadBudgets } = useApi(fetchBudgets);

  const fetchPrinters = useCallback(() => listPrinters(), []);
  const { data: printersData, reload: reloadPrinters } = useApi(fetchPrinters);

  // Unlinked jobs are the parent's escape hatch only — a child has nothing
  // to do with a plate that didn't match anything.
  const fetchJobs = useCallback(
    () => (isParent ? listPrintJobs({ unlinked: true }) : Promise.resolve([])),
    [isParent],
  );
  const { data: jobsData, reload: reloadJobs } = useApi(fetchJobs, [isParent]);

  const open = useMemo(() => normalizeList(openData), [openData]);
  const closed = useMemo(() => normalizeList(closedData), [closedData]);
  // The linker needs every request a job may bind to, which spans both lists.
  const requests = useMemo(() => [...open, ...closed], [open, closed]);
  // The server's own count, so a truncated history reads as "20 of 57"
  // rather than looking like the whole story.
  const closedTotal = closedData?.count ?? closed.length;
  const budgets = useMemo(() => normalizeList(budgetsData), [budgetsData]);
  const printers = useMemo(() => normalizeList(printersData), [printersData]);
  const unlinkedJobs = useMemo(() => normalizeList(jobsData), [jobsData]);

  const pending = open.filter((r) => r.status === 'pending');
  const printingCount = open.filter((r) => r.status === 'printing').length;

  const gramsUsed = budgets.reduce((sum, b) => sum + (Number(b.grams_used) || 0), 0);
  const { pct: budgetPct, label: budgetLabel } = budgetProgress(budgets);

  // A child only gets the live view while something of theirs is on the bed;
  // otherwise the panel would narrate a sibling's print.
  const activePrinters = printers.filter((p) => p.is_active !== false);
  const showLive = activePrinters.length > 0 && (isParent || printingCount > 0);

  const canCancel = (request) => (
    (isParent || request.user === user?.id)
    && (request.status === 'pending' || request.status === 'approved')
  );

  const doCancel = async () => {
    if (!pendingCancel) return;
    setBusy(true);
    setActionError('');
    try {
      await cancelPrintRequest(pendingCancel.id);
      setPendingCancel(null);
      reload();
    } catch (err) {
      setActionError(err?.message || 'Could not cancel that request.');
    } finally {
      setBusy(false);
    }
  };

  const afterDecision = () => {
    reload();
    reloadBudgets();
  };

  if (loading) return <Loader />;

  let rubricIndex = 0;
  const nextRubric = () => rubricIndex++;

  return (
    <div className="space-y-6">
      <QuestFolio
        letter="F"
        title="Forge"
        kicker="models, plates, filament"
        meta="ask · approve · slice · print"
        stats={[
          { value: pending.length, label: 'pending' },
          { value: printingCount, label: 'printing' },
          { value: Math.round(gramsUsed), label: 'grams' },
        ]}
        progressPct={budgetPct}
        progressLabel={budgetLabel}
      >
        <ErrorAlert message={error || actionError} />

        {!isParent && (
          <div className="flex justify-end">
            <Button
              size="sm"
              onClick={() => setSubmitOpen(true)}
              className="flex items-center gap-1 shrink-0"
            >
              <Plus size={16} /> Ask for a print
            </Button>
          </div>
        )}

        {isParent && pending.length > 0 && (
          <section>
            <ChapterRubric index={nextRubric()} name="Awaiting your decision" />
            <div className="space-y-2">
              {pending.map((request) => (
                <PrintRequestCard
                  key={request.id}
                  request={request}
                  showOwner
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
          <ChapterRubric index={nextRubric()} name="In the queue" />
          {open.length === 0 ? (
            <EmptyState icon={<Box size={28} />}>
              {isParent
                ? 'No open print requests right now.'
                : 'Nothing in the queue. Find a model you like and ask for it.'}
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
                    canDecide={isParent && request.status === 'pending'}
                    canCancel={canCancel(request)}
                    onDecide={setDeciding}
                    onCancel={setPendingCancel}
                  />
                ))}
            </div>
          )}
        </section>

        {showLive && (
          <section>
            <ChapterRubric index={nextRubric()} name="On the bed" />
            <div className="space-y-2">
              {activePrinters.map((printer) => (
                <PrinterStatus key={printer.id} printer={printer} />
              ))}
            </div>
          </section>
        )}

        {isParent && (
          <section>
            <ChapterRubric index={nextRubric()} name="Monthly budgets" />
            <BudgetPanel budgets={budgets} onChanged={reloadBudgets} />
          </section>
        )}

        {isParent && (
          <section>
            <ChapterRubric index={nextRubric()} name="Prints without a request" />
            <UnlinkedJobsPanel
              jobs={unlinkedJobs}
              requests={requests}
              onLinked={() => { reloadJobs(); reload(); }}
            />
          </section>
        )}

        {isParent && (
          <section>
            <ChapterRubric index={nextRubric()} name="Printers" />
            <PrinterConfigPanel printers={printers} onChanged={reloadPrinters} />
          </section>
        )}

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
                />
              ))}
            </div>
          </section>
        )}
      </QuestFolio>

      {submitOpen && (
        <PrintRequestModal
          onClose={() => setSubmitOpen(false)}
          onSaved={() => { setSubmitOpen(false); reload(); }}
          printers={printers}
        />
      )}

      {deciding && (
        <ApprovalSheet
          request={deciding}
          onClose={() => setDeciding(null)}
          onDecided={afterDecision}
        />
      )}

      {pendingCancel && (
        <ConfirmDialog
          title="Cancel this print request?"
          message={`“${pendingCancel.title}” goes away. They can always ask again.`}
          confirmLabel={busy ? 'Cancelling…' : 'Cancel it'}
          onConfirm={doCancel}
          onCancel={() => setPendingCancel(null)}
        />
      )}
    </div>
  );
}
