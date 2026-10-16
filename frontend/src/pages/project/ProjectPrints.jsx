import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { getAllApprovalPages, listPrintBudgets, listPrintRequests, listPrinters } from '../../api';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import { normalizeList } from '../../utils/api';
import Button from '../../components/Button';
import EmptyState from '../../components/EmptyState';
import ErrorAlert from '../../components/ErrorAlert';
import Loader from '../../components/Loader';
import SectionHeader from '../../components/SectionHeader';
import PrintRequestCard from '../forge/PrintRequestCard';
import PrintRequestModal from '../forge/PrintRequestModal';
import usePrintRequestRefresh from '../forge/usePrintRequestRefresh';

// ProjectDetail supplies a freshly loaded project and remounts its whole
// subtree when the project or authenticated account/credential changes.
export default function ProjectPrints({ project }) {
  const { user, isChild, isParent } = useRole();
  const [requestOpen, setRequestOpen] = useState(false);
  const { data, loading, refreshing, error, reload, setData } = useApi(
    () => getAllApprovalPages(() => listPrintRequests({ project_id: project.id })),
    [project.id],
  );
  const { data: budgetsData } = useApi(
    () => isChild ? listPrintBudgets() : Promise.resolve([]), [isChild],
  );
  const { data: printersData } = useApi(
    () => isChild ? listPrinters() : Promise.resolve([]), [isChild],
  );
  const requests = normalizeList(data);
  usePrintRequestRefresh({ requests, reload, paused: requestOpen });
  const budget = normalizeList(budgetsData).find((row) => row.user === user?.id);

  const applySaved = (saved) => {
    // The successful create response is already server-confirmed. Retain it
    // even if a later read is unavailable, without inventing a project link.
    setData((rows) => [saved, ...normalizeList(rows).filter((row) => row.id !== saved.id)]);
  };

  return (
    <section className="space-y-3">
      <SectionHeader
        title="3D printed parts"
        actions={isChild && (
          <Button size="sm" disabled={loading || refreshing} onClick={() => setRequestOpen(true)} className="inline-flex items-center justify-center gap-2">
            <Plus size={16} /> Request a part
          </Button>
        )}
      >
        {isChild ? 'Request a model for this project and follow its progress here.'
          : 'Follow the print requests for this project.'}
      </SectionHeader>
      <p className="font-body text-caption text-ink-secondary">
        {isChild ? 'You can accept coin quotes and manage requests in 3D prints under Rewards.'
          : 'Review requests in Today or manage them in 3D prints under Rewards.'}
      </p>
      <Link to="/treasury?tab=forge" className="inline-flex min-h-11 items-center font-body text-body text-sheikah-teal-deep hover:underline">
        View all 3D prints
      </Link>
      {loading && <Loader />}
      {error && (
        <div className="space-y-2">
          <ErrorAlert message={error} />
          <Button variant="secondary" size="sm" onClick={reload}>Retry project prints</Button>
        </div>
      )}
      {!loading && !error && requests.length === 0 && <EmptyState>No prints requested for this project yet.</EmptyState>}
      {requests.map((request) => (
        <PrintRequestCard key={request.id} request={request} showOwner={isParent} showPlateFilename={isParent} />
      ))}
      {isChild && requestOpen && (
        <PrintRequestModal
          project={project}
          budget={budget}
          printers={normalizeList(printersData)}
          onSaved={applySaved}
          onClose={() => setRequestOpen(false)}
        />
      )}
    </section>
  );
}
