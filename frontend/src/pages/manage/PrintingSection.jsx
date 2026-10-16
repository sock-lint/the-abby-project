import { Link } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import { getToken } from '../../api/client';
import {
  getAllApprovalPages, listPrintBudgets, listPrintJobs, listPrintRequests, listPrinters,
} from '../../api';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import SectionHeader from '../../components/SectionHeader';
import BudgetPanel from '../forge/BudgetPanel';
import PrinterConfigPanel from '../forge/PrinterConfigPanel';
import PrinterStatus from '../forge/PrinterStatus';
import UnlinkedJobsPanel from '../forge/UnlinkedJobsPanel';
import { LINKABLE_REQUEST_STATUSES } from '../forge/forge.constants';

const fetchBudgets = () => getAllApprovalPages(listPrintBudgets);
const fetchPrinters = () => getAllApprovalPages(listPrinters);
const fetchRequests = () => getAllApprovalPages(() => listPrintRequests({ status: LINKABLE_REQUEST_STATUSES.join(',') }));
const fetchJobs = () => getAllApprovalPages(() => listPrintJobs({ unlinked: true }));
const fetchDismissed = () => getAllApprovalPages(() => listPrintJobs({ unlinked: true, dismissed: true }));

export default function PrintingSection() {
  const { user, isParent } = useRole();
  if (!isParent) return <p>Printing settings are available to parents.</p>;
  return <PrintingManagement key={`${user.id}:${user.family?.id ?? ''}:${getToken()}`} />;
}

function PrintingManagement() {
  const budgets = useApi(fetchBudgets);
  const printers = useApi(fetchPrinters);
  const requests = useApi(fetchRequests);
  const jobs = useApi(fetchJobs);
  const dismissed = useApi(fetchDismissed);
  const sources = [budgets, printers, requests, jobs, dismissed];
  const reload = () => sources.forEach((source) => source.reload());
  const loading = sources.some((source) => source.loading);
  const error = sources.find((source) => source.error)?.error;
  const activePrinters = (printers.data || []).filter((printer) => printer.is_active !== false);

  return (
    <section aria-label="Printing settings" className="space-y-6">
      <SectionHeader title="3D Printing" kicker="Family printer setup and limits" />
      <Link to="/treasury?tab=forge" className="inline-flex min-h-11 items-center font-semibold text-sheikah-teal-deep underline">
        Review print requests
      </Link>
      <ErrorAlert message={error ? `Could not load all printing settings. ${error}` : null} onRetry={reload} />
      {loading ? <Loader /> : (
        <>
          <section className="space-y-3">
            <SectionHeader as="h3" title="Monthly budgets" />
            {!budgets.error && <BudgetPanel budgets={budgets.data || []} onChanged={budgets.reload} />}
          </section>
          {activePrinters.length > 0 && <section className="space-y-3">
            <SectionHeader as="h3" title="Printer status" />
            {activePrinters.map((printer) => (
              <PrinterStatus key={printer.id} printer={printer} />
            ))}
          </section>}
          <section className="space-y-3">
            <SectionHeader as="h3" title="Printers" />
            {!printers.error && <PrinterConfigPanel printers={printers.data || []} onChanged={printers.reload} />}
          </section>
          <section className="space-y-3">
            <SectionHeader as="h3" title="Prints without a request" />
            {!jobs.error && !dismissed.error && !requests.error && (
              <UnlinkedJobsPanel jobs={jobs.data || []} dismissedJobs={dismissed.data || []}
                requests={requests.data || []} onLinked={reload} onChanged={reload} />
            )}
          </section>
        </>
      )}
    </section>
  );
}
