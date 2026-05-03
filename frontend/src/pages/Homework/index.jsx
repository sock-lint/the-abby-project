import { useState, useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus } from 'lucide-react';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import {
  getHomeworkDashboard,
  approveHomeworkSubmission,
  rejectHomeworkSubmission,
  planHomework, getChildren,
  deleteHomework,
} from '../../api';
import { normalizeList } from '../../utils/api';
import ApprovalQueue from '../../components/ApprovalQueue';
import Loader from '../../components/Loader';
import ErrorAlert from '../../components/ErrorAlert';
import ConfirmDialog from '../../components/ConfirmDialog';
import HomeworkSubmitSheet from '../../components/HomeworkSubmitSheet';
import TimelinessBadge from '../../components/TimelinessBadge';
import ProofGallery from '../../components/ProofGallery';
import StatusBadge from '../../components/StatusBadge';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';
import AssignmentCard from './AssignmentCard';
import HomeworkFormModal from './HomeworkFormModal';

export default function Homework() {
  const { isParent } = useRole();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const { data: dashboard, loading, error, reload } = useApi(getHomeworkDashboard);
  // useApi's default deps=[] means a first call during auth-load (isParent=false)
  // would freeze apiFn=null and never re-fetch when isParent later flips. Pass
  // [isParent] so the call re-runs once auth resolves — matches the Chores /
  // Habits pattern. Empty resolver instead of `null` so the test's unblocked
  // AuthProvider doesn't error on `null(controller.signal)`.
  const { data: childrenData } = useApi(
    isParent ? getChildren : () => Promise.resolve({ results: [] }),
    [isParent],
  );
  const children = normalizeList(childrenData);

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [actionError, setActionError] = useState('');
  const [showSubmit, setShowSubmit] = useState(null);
  const [planning, setPlanning] = useState(null);
  const [planError, setPlanError] = useState('');

  const openCreate = () => { setEditing(null); setShowForm(true); };
  const openEdit = (a) => { setEditing(a); setShowForm(true); };
  const closeForm = () => { setShowForm(false); setEditing(null); };

  const didAutoOpen = useRef(false);
  useEffect(() => {
    if (!didAutoOpen.current && searchParams.get('new') === '1') {
      didAutoOpen.current = true;
      openCreate();
      searchParams.delete('new');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const handleApprove = async (id) => {
    await approveHomeworkSubmission(id);
    reload();
  };

  const handleReject = async (id) => {
    await rejectHomeworkSubmission(id);
    reload();
  };

  const handleDelete = async () => {
    setActionError('');
    try {
      await deleteHomework(deleteConfirm);
      setDeleteConfirm(null);
      reload();
    } catch (err) {
      setActionError(err?.message || 'Could not delete the assignment.');
    }
  };

  const handlePlan = async (assignment) => {
    setPlanning(assignment.id);
    setPlanError('');
    try {
      const result = await planHomework(assignment.id);
      const projectId = result?.project_id || result?.project?.id || result?.project;
      if (projectId) {
        // Audit H9: SPA navigation rather than ``window.location.href``,
        // which tore down all React state, refetched ``/api/auth/me/``,
        // and briefly flashed the prior shell under PWA. ``useNavigate``
        // keeps the auth context, the sprite catalog, and the cached
        // dashboard data warm.
        navigate(`/quests/ventures/${projectId}`);
        return;
      }
      reload();
    } catch (err) {
      setPlanError(err?.message || 'AI planning failed. Try again later.');
    } finally {
      setPlanning(null);
    }
  };

  if (loading) return <Loader />;
  if (error) return <ErrorAlert message={error} />;

  const renderCard = (a) => (
    <AssignmentCard
      key={a.id} assignment={a}
      onSubmit={() => setShowSubmit(a)}
      onPlan={() => handlePlan(a)}
      planning={planning === a.id}
      canPlan={a.can_plan}
      canManage={isParent}
      onEdit={() => openEdit(a)}
      onDelete={() => setDeleteConfirm(a.id)}
    />
  );

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            study · scholar's corner
          </div>
          <h2 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight">
            Study
          </h2>
          <div className="font-script text-sm text-ink-whisper mt-1 max-w-xl">
            submit each assignment with a proof photo · approval awards XP through the skill tags
          </div>
        </div>
        <Button
          size="sm"
          onClick={openCreate}
          className="flex items-center gap-1"
        >
          <Plus size={14} /> New assignment
        </Button>
      </header>

      {actionError && <ErrorAlert message={actionError} />}
      {planError && <ErrorAlert message={planError} />}

      {/* Child dashboard view */}
      {!isParent && (
        <>
          {dashboard?.overdue?.length > 0 && (
            <div className="bg-ember/15 border border-ember/50 rounded-lg p-3 font-body text-ember-deep text-sm">
              {dashboard.overdue.length} overdue assignment{dashboard.overdue.length > 1 ? 's' : ''}
            </div>
          )}

          {dashboard?.stats && (
            <div className="grid grid-cols-3 gap-3">
              <StatTile label="Completion" value={`${dashboard.stats.completion_rate}%`} />
              <StatTile label="On time" value={`${dashboard.stats.on_time_rate}%`} />
              <StatTile label="Approved" value={dashboard.stats.total_approved} />
            </div>
          )}

          <Section title="Due today" items={dashboard?.today} emptyText="Nothing due today.">
            {renderCard}
          </Section>

          {dashboard?.overdue?.length > 0 && (
            <Section title="Overdue" items={dashboard.overdue}>
              {renderCard}
            </Section>
          )}

          <Section title="Coming up" items={dashboard?.upcoming} emptyText="No upcoming assignments.">
            {renderCard}
          </Section>
        </>
      )}

      {/* Parent view */}
      {isParent && (
        <>
        {dashboard?.assignments?.length > 0 && (
          <Section title="Active assignments" items={dashboard.assignments}>
            {(a) => (
              <AssignmentCard
                key={a.id} assignment={a}
                onPlan={() => handlePlan(a)}
                planning={planning === a.id}
                canPlan={a.can_plan}
                canManage
                onEdit={() => openEdit(a)}
                onDelete={() => setDeleteConfirm(a.id)}
              />
            )}
          </Section>
        )}
        <ApprovalQueue
          items={dashboard?.pending_submissions}
          title="Awaiting your seal"
          emptyText="No pending submissions."
          onApprove={handleApprove}
          onReject={handleReject}
        >
          {({ item: sub, actions }) => (
            <ParchmentCard key={sub.id} className="space-y-3">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="font-body">
                  <span className="font-medium text-ink-primary">{sub.user_name}</span>
                  <span className="text-ink-whisper mx-2">&mdash;</span>
                  <span className="text-ink-primary">{sub.assignment_title}</span>
                </div>
                <div className="flex gap-1.5 flex-wrap">
                  <TimelinessBadge timeliness={sub.timeliness} />
                  <StatusBadge status={sub.status} />
                </div>
              </div>
              {sub.notes && (
                <p className="font-script text-sm text-ink-secondary italic">
                  &ldquo;{sub.notes}&rdquo;
                </p>
              )}
              <ProofGallery proofs={sub.proofs} />
              <div className="flex items-center justify-end gap-1.5 flex-wrap">
                {actions}
              </div>
            </ParchmentCard>
          )}
        </ApprovalQueue>
        </>
      )}

      {showForm && (
        <HomeworkFormModal
          assignment={editing}
          isParent={isParent}
          children={children}
          onClose={closeForm}
          onSaved={() => { closeForm(); reload(); }}
        />
      )}

      {deleteConfirm && (
        <ConfirmDialog
          title="Delete assignment?"
          message="Past submissions (if any) stay in the approval history, but the assignment itself will be hidden."
          onConfirm={handleDelete}
          onCancel={() => setDeleteConfirm(null)}
        />
      )}

      <HomeworkSubmitSheet
        assignment={showSubmit}
        onClose={() => setShowSubmit(null)}
        onSubmitted={() => { setShowSubmit(null); reload(); }}
      />
    </div>
  );
}

function StatTile({ label, value }) {
  return (
    <ParchmentCard className="text-center py-3">
      <div className="font-display font-semibold text-2xl text-ink-primary tabular-nums">{value}</div>
      <div className="font-script text-xs text-ink-whisper uppercase tracking-wider">{label}</div>
    </ParchmentCard>
  );
}

function Section({ title, items, emptyText, children }) {
  return (
    <section>
      <h2 className="font-display text-xl text-ink-primary leading-tight mb-3">{title}</h2>
      {!items?.length ? (
        emptyText && <p className="font-script text-sm text-ink-whisper italic">{emptyText}</p>
      ) : (
        <div className="space-y-2">
          <AnimatePresence>
            {items.map((item) => (
              <motion.div
                key={item.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                {children(item)}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </section>
  );
}
