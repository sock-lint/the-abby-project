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
import { useConfirmState } from '../hooks/useConfirmState';
import { useRole } from '../hooks/useRole';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
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
  const { data: project, loading, reload } = useApi(() => getProject(id), [id]);
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
  const { confirmState, askConfirm, closeConfirm } = useConfirmState();

  if (loading) return <Loader />;
  if (!project) return (
    <div className="text-center py-12 font-script text-ink-whisper italic">
      This venture is not inscribed in the journal.
    </div>
  );

  const isAssigned = project.assigned_to?.id === user?.id;

  const openAddStep = (milestoneId = null) => {
    setAddStepMilestoneId(milestoneId);
    setAddStepOpen(true);
  };

  const handleMoveStep = async (step, newMilestoneId) => {
    const value = newMilestoneId === '' ? null : Number(newMilestoneId);
    if (value === (step.milestone ?? null)) return;
    await updateStep(id, step.id, { milestone: value });
    reload();
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

  const handleCompleteMilestone = async (msId) => {
    await completeMilestone(id, msId);
    reload();
  };

  const handleMarkPurchased = async (matId, cost) => {
    await markPurchased(id, matId, cost);
    reload();
  };

  const handleToggleStep = async (step) => {
    if (step.is_completed) await uncompleteStep(id, step.id);
    else await completeStep(id, step.id);
    reload();
  };

  const handleDeleteMilestone = (msId) =>
    askConfirm({
      title: 'Delete this milestone?',
      message: 'This action cannot be undone.',
      onConfirm: async () => { await deleteMilestone(id, msId); reload(); },
    });

  const handleDeleteMaterial = (matId) =>
    askConfirm({
      title: 'Delete this material?',
      message: 'This action cannot be undone.',
      onConfirm: async () => { await deleteMaterial(id, matId); reload(); },
    });

  const handleDeleteStep = (stepId) =>
    askConfirm({
      title: 'Delete this step?',
      message: 'Any attached resources will also be removed.',
      onConfirm: async () => { await deleteStep(id, stepId); reload(); },
    });

  const handleDeleteResource = (resId) =>
    askConfirm({
      title: 'Delete this resource?',
      message: 'This action cannot be undone.',
      onConfirm: async () => { await deleteResource(id, resId); reload(); },
    });

  return (
    <div className="space-y-6">
      <ProjectHeader
        project={project}
        isParent={isParent}
        isAssigned={isAssigned}
        onAction={handleAction}
        onEdit={() => setEditOpen(true)}
        onOpenQR={() => setQrOpen(true)}
      />

      <ErrorAlert message={error} />

      <p className="font-script text-sm text-ink-whisper text-center">
        plan the chapters, gather the materials, then clock hours from the timer
      </p>

      <div className="flex gap-1 bg-ink-page-aged rounded-lg p-1 border border-ink-page-shadow">
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-2 rounded-md font-display text-sm transition-colors ${
              activeTab === tab
                ? 'bg-sheikah-teal-deep text-ink-page-rune-glow'
                : 'text-ink-secondary hover:text-ink-primary'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

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
