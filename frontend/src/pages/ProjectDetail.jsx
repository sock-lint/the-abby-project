import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  getProject, submitProject, approveProject, requestChanges,
  completeMilestone, deleteMilestone,
  markPurchased, deleteMaterial,
  activateProject,
  completeStep, uncompleteStep, updateStep, deleteStep,
  deleteResource,
} from '../api';
import { useApi } from '../hooks/useApi';
import { formatCurrency } from '../utils/format';
import { useConfirmState } from '../hooks/useConfirmState';
import { useRole } from '../hooks/useRole';
import ConfirmDialog from '../components/ConfirmDialog';
import BackLink from '../components/BackLink';
import Button from '../components/Button';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import ParchmentSkeleton from '../components/ParchmentSkeleton';
import TabList from '../components/layout/TabList';
import ProjectHeader from './project/ProjectHeader';
import OverviewTab from './project/OverviewTab';
import PlanTab from './project/PlanTab';
import MaterialsTab from './project/MaterialsTab';
import EditProjectModal from './project/modals/EditProjectModal';
import AddMilestoneModal from './project/modals/AddMilestoneModal';
import AddMaterialModal from './project/modals/AddMaterialModal';
import AddStepModal from './project/modals/AddStepModal';
import AddResourceModal from './project/modals/AddResourceModal';
import RequestChangesModal from './project/modals/RequestChangesModal';
import ProjectQRSheet from './project/modals/ProjectQRSheet';

const tabs = ['Overview', 'Plan', 'Materials'];

export default function ProjectDetail() {
  const { user, isParent } = useRole();
  const { id } = useParams();
  const { data: project, loading, error: loadError, reload } = useApi(() => getProject(id), [id]);
  const [activeTab, setActiveTab] = useState('Overview');
  const [changesOpen, setChangesOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [addMilestoneOpen, setAddMilestoneOpen] = useState(false);
  const [addMaterialOpen, setAddMaterialOpen] = useState(false);
  const [addStepOpen, setAddStepOpen] = useState(false);
  const [addStepMilestoneId, setAddStepMilestoneId] = useState(null);
  const [addResourceOpen, setAddResourceOpen] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);
  const [error, setError] = useState('');
  // Pending milestone-completion id — surfaces an in-flight visual on the
  // milestone-complete circle in PlanTab so a slow network doesn't read as
  // a dead tap.
  const [pendingMilestoneId, setPendingMilestoneId] = useState(null);
  const { confirmState, askConfirm, closeConfirm } = useConfirmState();

  if (loading) return (
    <div className="space-y-6">
      <ParchmentSkeleton variant="hero" />
      <ParchmentSkeleton variant="list" count={3} />
    </div>
  );
  // A failed fetch is not a missing venture. Without this branch a tunnel or a
  // dropped wifi frame renders the "may have been deleted" copy below, telling
  // a kid their project is gone and offering no way back.
  if (loadError) return (
    <div className="space-y-4">
      <BackLink to="/quests?tab=ventures">Back to Ventures</BackLink>
      <ErrorAlert message={loadError} />
      <Button variant="primary" onClick={reload}>
        Try again
      </Button>
    </div>
  );
  if (!project) return (
    <div className="space-y-4">
      <BackLink to="/quests?tab=ventures">Back to Ventures</BackLink>
      <EmptyState>
        This venture is not inscribed in the journal — it may have been deleted, or the link points to a different family&apos;s page.
      </EmptyState>
    </div>
  );

  const isAssigned = project.assigned_to?.id === user?.id;

  const openAddStep = (milestoneId = null) => {
    setAddStepMilestoneId(milestoneId);
    setAddStepOpen(true);
  };

  // Every mutation on this page routes its failure into the page-level
  // ErrorAlert. Without the catch a flaky network turned a step tap, a
  // purchase tick or a delete into a silent no-op that looked exactly like
  // success — the row simply didn't move and nothing said why.
  const runAction = async (fn) => {
    setError('');
    try {
      await fn();
      reload();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleMoveStep = (step, newMilestoneId) => {
    const value = newMilestoneId === '' ? null : Number(newMilestoneId);
    if (value === (step.milestone ?? null)) return;
    return runAction(() => updateStep(id, step.id, { milestone: value }));
  };

  const handleAction = async (action) => {
    setError('');
    try {
      if (action === 'activate') await activateProject(id);
      else if (action === 'submit') await submitProject(id);
      else if (action === 'approve') await approveProject(id);
      else if (action === 'request-changes') {
        setChangesOpen(true);
        return;
      }
      reload();
    } catch (err) {
      setError(err.message);
    }
  };

  const submitRequestChanges = async (notes) => {
    setError('');
    try {
      await requestChanges(id, notes);
      setChangesOpen(false);
      reload();
    } catch (err) {
      setError(err.message);
    }
  };

  // Completing a milestone posts a milestone_bonus to PaymentLedger, so it is
  // a payout, not a checkbox — and the circle sits right beside the accordion
  // toggle. Confirm first, like every other irreversible action on this page.
  const handleCompleteMilestone = (msId) => {
    if (pendingMilestoneId) return;
    const ms = (project.milestones || []).find((m) => m.id === msId);
    const bonus = ms?.bonus_amount ? ` and pay the ${formatCurrency(ms.bonus_amount)} bonus` : '';
    askConfirm({
      title: 'Mark this milestone complete?',
      message: `This will close out “${ms?.title || 'this milestone'}”${bonus}. It can't be undone.`,
      confirmLabel: 'Mark complete',
      onConfirm: async () => {
        setPendingMilestoneId(msId);
        try {
          await completeMilestone(id, msId);
          reload();
        } catch (err) {
          setError(err.message);
        } finally {
          setPendingMilestoneId(null);
        }
      },
    });
  };

  const handleMarkPurchased = (matId, cost) =>
    runAction(() => markPurchased(id, matId, cost));

  const handleToggleStep = (step) =>
    runAction(() => (step.is_completed
      ? uncompleteStep(id, step.id)
      : completeStep(id, step.id)));

  const handleDeleteMilestone = (msId) =>
    askConfirm({
      title: 'Delete this milestone?',
      message: 'This action cannot be undone.',
      onConfirm: () => runAction(() => deleteMilestone(id, msId)),
    });

  const handleDeleteMaterial = (matId) =>
    askConfirm({
      title: 'Delete this material?',
      message: 'This action cannot be undone.',
      onConfirm: () => runAction(() => deleteMaterial(id, matId)),
    });

  const handleDeleteStep = (stepId) =>
    askConfirm({
      title: 'Delete this step?',
      message: 'Any attached resources will also be removed.',
      onConfirm: () => runAction(() => deleteStep(id, stepId)),
    });

  const handleDeleteResource = (resId) =>
    askConfirm({
      title: 'Delete this resource?',
      message: 'This action cannot be undone.',
      onConfirm: () => runAction(() => deleteResource(id, resId)),
    });

  return (
    <div className="space-y-6">
      <BackLink to="/quests?tab=ventures">Back to Ventures</BackLink>

      <ProjectHeader
        project={project}
        isParent={isParent}
        isAssigned={isAssigned}
        onAction={handleAction}
        onEdit={() => setEditOpen(true)}
        onOpenQR={() => setQrOpen(true)}
      />

      <ErrorAlert message={error} />

      <TabList
        tabs={tabs.map((id) => ({ id, label: id }))}
        activeId={activeTab}
        onSelect={setActiveTab}
        variant="pill"
        ariaLabel="Project sections"
        stretch
        scrollFades={false}
      />

      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
        >
          {activeTab === 'Overview' && (
            <OverviewTab project={project} isParent={isParent} />
          )}
          {activeTab === 'Plan' && (
            <PlanTab
              project={project}
              isParent={isParent}
              pendingMilestoneId={pendingMilestoneId}
              onCompleteMilestone={handleCompleteMilestone}
              onDeleteMilestone={handleDeleteMilestone}
              onToggleStep={handleToggleStep}
              onDeleteStep={handleDeleteStep}
              onMoveStep={handleMoveStep}
              onDeleteResource={handleDeleteResource}
              onOpenAddMilestone={() => setAddMilestoneOpen(true)}
              onOpenAddStep={openAddStep}
              onOpenAddResource={() => setAddResourceOpen(true)}
            />
          )}
          {activeTab === 'Materials' && (
            <MaterialsTab
              project={project}
              isParent={isParent}
              onMarkPurchased={handleMarkPurchased}
              onDeleteMaterial={handleDeleteMaterial}
              onOpenAddMaterial={() => setAddMaterialOpen(true)}
            />
          )}
        </motion.div>
      </AnimatePresence>

      <AnimatePresence>
        {changesOpen && (
          <RequestChangesModal
            onClose={() => setChangesOpen(false)}
            onSubmit={submitRequestChanges}
          />
        )}
        {editOpen && (
          <EditProjectModal
            project={project}
            onClose={() => setEditOpen(false)}
            onSaved={() => { setEditOpen(false); reload(); }}
          />
        )}
        {addMilestoneOpen && (
          <AddMilestoneModal
            projectId={id}
            onClose={() => setAddMilestoneOpen(false)}
            onSaved={() => { setAddMilestoneOpen(false); reload(); }}
          />
        )}
        {addMaterialOpen && (
          <AddMaterialModal
            projectId={id}
            onClose={() => setAddMaterialOpen(false)}
            onSaved={() => { setAddMaterialOpen(false); reload(); }}
          />
        )}
        {addStepOpen && (
          <AddStepModal
            projectId={id}
            milestones={project.milestones || []}
            initialMilestoneId={addStepMilestoneId}
            onClose={() => setAddStepOpen(false)}
            onSaved={() => { setAddStepOpen(false); reload(); }}
          />
        )}
        {addResourceOpen && (
          <AddResourceModal
            projectId={id}
            steps={project.steps || []}
            onClose={() => setAddResourceOpen(false)}
            onSaved={() => { setAddResourceOpen(false); reload(); }}
          />
        )}
        {qrOpen && (
          <ProjectQRSheet
            projectId={id}
            projectTitle={project.title}
            onClose={() => setQrOpen(false)}
          />
        )}
      </AnimatePresence>

      {confirmState && (
        <ConfirmDialog
          title={confirmState.title}
          message={confirmState.message}
          confirmLabel={confirmState.confirmLabel}
          onConfirm={async () => {
            const fn = confirmState.onConfirm;
            closeConfirm();
            await fn();
          }}
          onCancel={closeConfirm}
        />
      )}
    </div>
  );
}
