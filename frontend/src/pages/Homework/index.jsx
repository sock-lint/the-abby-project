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
  withdrawHomeworkSubmission,
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
import ChapterRubric from '../../components/atlas/ChapterRubric';
import Button from '../../components/Button';
import AssignmentCard from './AssignmentCard';
import HomeworkFormModal from './HomeworkFormModal';
import QuestFolio from '../quests/QuestFolio';
import { buildRarityCounts, effortToRarity } from '../quests/quests.constants';

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

  const handleWithdraw = async (submissionId) => {
    setActionError('');
    try {
      await withdrawHomeworkSubmission(submissionId);
      reload();
    } catch (err) {
      setActionError(err?.message || 'Could not withdraw that submission.');
    }
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
      onWithdraw={isParent ? undefined : handleWithdraw}
    />
  );

  // Verso math — child: completion / on-time rates (from dashboard.stats);
  // parent: assignment + pending counts. Rarity strand reads effort_level
  // across whatever's visible on the recto (today/overdue/upcoming for
  // child, assignments for parent).
  const stats = dashboard?.stats ?? {};
  const allAssignments = isParent
    ? (dashboard?.assignments ?? [])
    : [
      ...(dashboard?.today ?? []),
      ...(dashboard?.overdue ?? []),
      ...(dashboard?.upcoming ?? []),
    ];
  const pendingSubs = dashboard?.pending_submissions ?? [];
  const versoStats = isParent
    ? [
      { value: pendingSubs.length, label: 'awaiting seal' },
      { value: allAssignments.length, label: 'active' },
    ]
    : [
      { value: `${stats.completion_rate ?? 0}%`, label: 'completion' },
      { value: `${stats.on_time_rate ?? 0}%`, label: 'on time' },
    ];
  const versoProgressPct = isParent
    ? (allAssignments.length === 0 ? 0
      : Math.round(100 * (1 - pendingSubs.length / Math.max(1, allAssignments.length + pendingSubs.length))))
    : Number(stats.completion_rate || 0);
  const versoProgressLabel = isParent
    ? (pendingSubs.length === 0
      ? 'queue is clear'
      : `${pendingSubs.length} submission${pendingSubs.length === 1 ? '' : 's'} pending`)
    : `${stats.total_approved ?? 0} approved this year`;
  const versoRarityCounts = allAssignments.length > 0
    ? buildRarityCounts(
      allAssignments,
      (a) => effortToRarity(a.effort_level),
      (a) => a.submission_status === 'approved',
    )
    : undefined;

  let rubricIndex = 0;
  const nextRubric = () => rubricIndex++;

  return (
    <div className="space-y-6">
      <QuestFolio
        letter="S"
        title="Study"
        kicker="the scholar's corner"
        meta="submit each assignment with a proof photo"
        stats={versoStats}
        progressPct={versoProgressPct}
        progressLabel={versoProgressLabel}
        rarityCounts={versoRarityCounts}
      >
        {actionError && <ErrorAlert message={actionError} />}
        {planError && <ErrorAlert message={planError} />}

        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={openCreate}
            className="flex items-center gap-1"
          >
            <Plus size={14} /> New assignment
          </Button>
        </div>

        {/* Child dashboard view */}
        {!isParent && (
          <>
            {dashboard?.overdue?.length > 0 && (
              <div className="bg-ember/15 border border-ember/50 rounded-lg p-3 font-body text-ember-deep text-sm">
                {dashboard.overdue.length} overdue assignment{dashboard.overdue.length > 1 ? 's' : ''}
              </div>
            )}

            <Section
              index={nextRubric()}
              title="Due today"
              items={dashboard?.today}
              emptyText="Nothing due today."
            >
              {renderCard}
            </Section>

            {dashboard?.overdue?.length > 0 && (
              <Section index={nextRubric()} title="Overdue" items={dashboard.overdue}>
                {renderCard}
              </Section>
            )}

            <Section
              index={nextRubric()}
              title="Coming up"
              items={dashboard?.upcoming}
              emptyText="No upcoming assignments."
            >
              {renderCard}
            </Section>
          </>
        )}

        {/* Parent view */}
        {isParent && (
          <>
            <Section
              index={nextRubric()}
              title="Active assignments"
              items={dashboard?.assignments}
              emptyText="No active assignments. Tap “New homework” to add one."
            >
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
            <section>
              <ChapterRubric index={nextRubric()} name="Awaiting your seal" />
              <ApprovalQueue
                items={dashboard?.pending_submissions}
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
            </section>
          </>
        )}
      </QuestFolio>

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

function Section({ index = 0, title, items, emptyText, children }) {
  return (
    <section>
      <ChapterRubric index={index} name={title} />
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
