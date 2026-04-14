import { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Check, ChevronDown, ExternalLink, ArrowLeft, DollarSign, QrCode, Copy,
  Pencil, Plus, Trash2, Download,
} from 'lucide-react';
import {
  getProject, submitProject, approveProject, requestChanges,
  completeMilestone, deleteMilestone,
  markPurchased, deleteMaterial,
  saveProjectAsTemplate, activateProject,
  completeStep, uncompleteStep, updateStep, deleteStep,
  deleteResource, getProjectQR,
} from '../api';
import { useApi } from '../hooks/useApi';
import BottomSheet from '../components/BottomSheet';
import Card from '../components/Card';
import StarRating from '../components/StarRating';
import EmptyState from '../components/EmptyState';
import Loader from '../components/Loader';
import ProgressBar from '../components/ProgressBar';
import StatusBadge from '../components/StatusBadge';
import { ResourcePill, StepCard } from './project/ProjectPlanItems';
import {
  EditProjectModal, AddMilestoneModal, AddMaterialModal, AddStepModal,
  AddResourceModal, RequestChangesModal,
} from './project/ProjectModals';

const tabs = ['Overview', 'Plan', 'Materials'];

const LOOSE_KEY = '__loose__';

export default function ProjectDetail({ user }) {
  const { id } = useParams();
  const navigate = useNavigate();
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
  const [qrUrl, setQrUrl] = useState(null);
  const [qrLoading, setQrLoading] = useState(false);
  const [collapsedMilestones, setCollapsedMilestones] = useState(() => new Set());

  // Group steps by milestone id (or LOOSE_KEY for unassigned). Memoized so
  // expanding/collapsing accordions doesn't re-run the partition.
  const stepsByMilestone = useMemo(() => {
    const map = new Map();
    for (const s of project?.steps || []) {
      const key = s.milestone ?? LOOSE_KEY;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(s);
    }
    return map;
  }, [project?.steps]);

  const handleQrOpen = async () => {
    setQrOpen(true);
    setQrLoading(true);
    try {
      const blob = await getProjectQR(id);
      setQrUrl(URL.createObjectURL(blob));
    } catch {
      setQrUrl(null);
    } finally {
      setQrLoading(false);
    }
  };

  const handleQrClose = () => {
    setQrOpen(false);
    if (qrUrl) {
      URL.revokeObjectURL(qrUrl);
      setQrUrl(null);
    }
  };

  if (loading) return <Loader />;
  if (!project) return <div className="text-forge-text-dim">Project not found</div>;

  const isParent = user?.role === 'parent';
  const isAssigned = project.assigned_to?.id === user?.id;
  const milestones = project.milestones || [];
  const looseSteps = stepsByMilestone.get(LOOSE_KEY) || [];

  const toggleMilestone = (msId) => {
    setCollapsedMilestones((prev) => {
      const next = new Set(prev);
      if (next.has(msId)) next.delete(msId);
      else next.add(msId);
      return next;
    });
  };

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
      alert(err.message);
    }
  };

  const submitRequestChanges = async (notes) => {
    try {
      await requestChanges(id, notes);
      setChangesOpen(false);
      reload();
    } catch (err) {
      alert(err.message);
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

  const handleDeleteMilestone = async (msId) => {
    if (!confirm('Delete this milestone?')) return;
    await deleteMilestone(id, msId);
    reload();
  };

  const handleDeleteMaterial = async (matId) => {
    if (!confirm('Delete this material?')) return;
    await deleteMaterial(id, matId);
    reload();
  };

  const handleToggleStep = async (step) => {
    if (step.is_completed) {
      await uncompleteStep(id, step.id);
    } else {
      await completeStep(id, step.id);
    }
    reload();
  };

  const handleDeleteStep = async (stepId) => {
    if (!confirm('Delete this step? Any attached resources will also be removed.')) return;
    await deleteStep(id, stepId);
    reload();
  };

  const handleDeleteResource = async (resId) => {
    if (!confirm('Delete this resource?')) return;
    await deleteResource(id, resId);
    reload();
  };

  return (
    <div className="space-y-6">
      <button onClick={() => navigate('/projects')} className="flex items-center gap-1 text-sm text-forge-text-dim hover:text-forge-text">
        <ArrowLeft size={16} /> Back to Projects
      </button>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold">{project.title}</h1>
          <div className="flex items-center gap-3 mt-1 text-sm text-forge-text-dim">
            <StatusBadge status={project.status} />
            {project.payment_kind === 'bounty' && (
              <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded bg-fuchsia-400/15 text-fuchsia-300 border border-fuchsia-400/30">
                Bounty
              </span>
            )}
            {project.category && <span>{project.category.icon} {project.category.name}</span>}
            <StarRating value={project.difficulty} />
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          {isParent && (project.status === 'draft' || project.status === 'active') && (
            <button onClick={() => handleAction('activate')} className="bg-amber-primary hover:bg-amber-highlight text-forge-bg px-4 py-2 rounded-lg text-sm font-medium">
              Activate Project
            </button>
          )}
          {isAssigned && project.status === 'in_progress' && (
            <button onClick={() => handleAction('submit')} className="bg-purple-600 hover:bg-purple-500 text-white px-4 py-2 rounded-lg text-sm font-medium">
              Submit for Review
            </button>
          )}
          {isParent && project.status === 'in_review' && (
            <>
              <button onClick={() => handleAction('approve')} className="bg-green-600 hover:bg-green-500 text-white px-4 py-2 rounded-lg text-sm font-medium">
                Approve
              </button>
              <button onClick={() => handleAction('request-changes')} className="bg-forge-muted hover:bg-forge-border text-forge-text px-4 py-2 rounded-lg text-sm font-medium">
                Request Changes
              </button>
            </>
          )}
          {isParent && project.status === 'completed' && (
            <button
              onClick={async () => {
                await saveProjectAsTemplate(project.id, false);
                alert('Saved as template!');
              }}
              className="bg-forge-muted hover:bg-forge-border text-forge-text px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-1"
            >
              <Copy size={14} /> Save as Template
            </button>
          )}
          {isParent && (
            <button
              onClick={() => setEditOpen(true)}
              className="bg-forge-muted hover:bg-forge-border text-forge-text px-3 py-2 rounded-lg text-sm font-medium flex items-center gap-1"
            >
              <Pencil size={14} /> Edit
            </button>
          )}
          <button
            onClick={handleQrOpen}
            className="bg-forge-muted hover:bg-forge-border text-forge-text px-3 py-2 rounded-lg text-sm font-medium flex items-center gap-1"
          >
            <QrCode size={14} /> QR
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-forge-card rounded-lg p-1 border border-forge-border">
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === tab
                ? 'bg-amber-primary/15 text-amber-highlight'
                : 'text-forge-text-dim hover:text-forge-text'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={activeTab} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
          {activeTab === 'Overview' && (
            <div className="space-y-4">
              {project.description && <Card><p className="text-sm">{project.description}</p></Card>}
              {project.instructables_url && (
                <Card>
                  <a
                    href={project.instructables_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-amber-highlight hover:underline text-sm"
                  >
                    <ExternalLink size={16} /> View on Instructables
                  </a>
                </Card>
              )}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Card>
                  <div className="text-xs text-forge-text-dim">
                    {project.payment_kind === 'bounty' ? 'Bounty' : 'Bonus'}
                  </div>
                  <div className={`font-heading font-bold text-lg ${project.payment_kind === 'bounty' ? 'text-fuchsia-300' : ''}`}>
                    ${project.bonus_amount}
                  </div>
                </Card>
                <Card>
                  <div className="text-xs text-forge-text-dim">Budget</div>
                  <div className="font-heading font-bold text-lg">${project.materials_budget}</div>
                </Card>
                <Card>
                  <div className="text-xs text-forge-text-dim">XP Reward</div>
                  <div className="font-heading font-bold text-lg">{project.xp_reward}</div>
                </Card>
                <Card>
                  <div className="text-xs text-forge-text-dim">Due Date</div>
                  <div className="font-heading font-bold text-lg">
                    {project.due_date || 'None'}
                  </div>
                </Card>
              </div>
              {project.assigned_to && (
                <Card>
                  <div className="text-xs text-forge-text-dim mb-1">Assigned To</div>
                  <div className="text-sm font-medium">{project.assigned_to.display_name || project.assigned_to.username}</div>
                  {project.hourly_rate_override && (
                    <div className="text-xs text-forge-text-dim mt-1">Rate override: ${project.hourly_rate_override}/hr</div>
                  )}
                </Card>
              )}
              {!project.assigned_to && project.payment_kind === 'bounty' && (
                <Card className="border-fuchsia-400/30">
                  <div className="text-xs text-fuchsia-300 font-medium">Open Bounty</div>
                  <div className="text-sm text-forge-text-dim mt-1">This bounty is available for any maker to pick up.</div>
                </Card>
              )}
              {isParent && project.parent_notes && (
                <Card className="border-amber-primary/30">
                  <div className="text-xs text-amber-highlight mb-1 font-medium">Parent Notes</div>
                  <p className="text-sm">{project.parent_notes}</p>
                </Card>
              )}
              {project.resources?.length > 0 && (
                <Card>
                  <div className="text-xs text-forge-text-dim mb-2 font-medium uppercase tracking-wide">
                    Resources
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {project.resources.map((r) => (
                      <ResourcePill key={r.id} resource={r} />
                    ))}
                  </div>
                </Card>
              )}
            </div>
          )}

          {activeTab === 'Plan' && (
            <div className="space-y-3">
              {isParent && (
                <div className="flex gap-2 flex-wrap">
                  <button
                    onClick={() => setAddMilestoneOpen(true)}
                    className="flex-1 min-w-[140px] flex items-center justify-center gap-2 py-2.5 rounded-lg border border-dashed border-forge-border text-sm text-forge-text-dim hover:text-forge-text hover:border-amber-primary transition-colors"
                  >
                    <Plus size={16} /> Add Milestone
                  </button>
                  <button
                    onClick={() => openAddStep(null)}
                    className="flex-1 min-w-[140px] flex items-center justify-center gap-2 py-2.5 rounded-lg border border-dashed border-forge-border text-sm text-forge-text-dim hover:text-forge-text hover:border-amber-primary transition-colors"
                  >
                    <Plus size={16} /> Add Step
                  </button>
                  <button
                    onClick={() => setAddResourceOpen(true)}
                    className="flex-1 min-w-[140px] flex items-center justify-center gap-2 py-2.5 rounded-lg border border-dashed border-forge-border text-sm text-forge-text-dim hover:text-forge-text hover:border-amber-primary transition-colors"
                  >
                    <Plus size={16} /> Add Resource
                  </button>
                </div>
              )}

              {milestones.length === 0 && (project.steps || []).length === 0 && (
                <EmptyState className="py-8">
                  No plan yet — add a milestone or a step to break this project down.
                </EmptyState>
              )}

              {/* Milestones with their nested steps. */}
              {milestones.map((ms) => {
                const childSteps = stepsByMilestone.get(ms.id) || [];
                const done = childSteps.filter((s) => s.is_completed).length;
                const total = childSteps.length;
                const collapsed = collapsedMilestones.has(ms.id);
                const allDone = total > 0 && done === total;
                return (
                  <motion.div key={ms.id} layout>
                    <Card className={ms.is_completed ? 'opacity-60' : ''}>
                      <div className="flex items-start gap-3">
                        <button
                          onClick={() => !ms.is_completed && handleCompleteMilestone(ms.id)}
                          disabled={ms.is_completed}
                          aria-label={ms.is_completed ? 'Milestone completed' : 'Mark milestone complete'}
                          className={`w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0 mt-0.5 transition-colors ${
                            ms.is_completed
                              ? 'bg-green-500 border-green-500'
                              : 'border-forge-muted hover:border-amber-primary'
                          }`}
                        >
                          {ms.is_completed && <Check size={14} className="text-white" />}
                        </button>
                        <button
                          onClick={() => toggleMilestone(ms.id)}
                          className="flex-1 min-w-0 text-left"
                        >
                          <div className="flex items-center gap-2">
                            <div className={`font-heading font-bold text-sm ${ms.is_completed ? 'line-through' : ''}`}>
                              {ms.title}
                            </div>
                            {ms.bonus_amount && (
                              <span className="text-xs text-green-400 flex items-center gap-0.5">
                                <DollarSign size={12} />{ms.bonus_amount}
                              </span>
                            )}
                            <ChevronDown
                              size={14}
                              className={`text-forge-text-dim ml-auto transition-transform ${collapsed ? '-rotate-90' : ''}`}
                            />
                          </div>
                          {ms.description && (
                            <div className="text-xs text-forge-text-dim mt-0.5">{ms.description}</div>
                          )}
                          {total > 0 && (
                            <div className="mt-2 flex items-center gap-2">
                              <ProgressBar value={done} max={total} className="flex-1" />
                              <span className="text-[10px] text-forge-text-dim shrink-0">
                                {done}/{total}
                              </span>
                            </div>
                          )}
                        </button>
                        {isParent && (
                          <button
                            onClick={() => handleDeleteMilestone(ms.id)}
                            className="text-forge-text-dim hover:text-red-400 p-1 transition-colors shrink-0"
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>

                      {!collapsed && (
                        <div className="mt-3 ml-9 space-y-2">
                          {allDone && !ms.is_completed && (
                            <button
                              onClick={() => handleCompleteMilestone(ms.id)}
                              className="w-full text-xs bg-amber-primary/15 hover:bg-amber-primary/25 text-amber-highlight border border-amber-primary/30 rounded-lg py-2 transition-colors"
                            >
                              All steps done — mark milestone complete?
                            </button>
                          )}
                          {childSteps.map((step) => (
                            <StepCard
                              key={step.id}
                              step={step}
                              isParent={isParent}
                              milestones={milestones}
                              onToggle={handleToggleStep}
                              onDelete={handleDeleteStep}
                              onMove={handleMoveStep}
                            />
                          ))}
                          {childSteps.length === 0 && (
                            <div className="text-xs text-forge-text-dim italic">
                              No steps in this milestone yet.
                            </div>
                          )}
                          {isParent && (
                            <button
                              onClick={() => openAddStep(ms.id)}
                              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg border border-dashed border-forge-border text-xs text-forge-text-dim hover:text-forge-text hover:border-amber-primary transition-colors"
                            >
                              <Plus size={12} /> Add step here
                            </button>
                          )}
                        </div>
                      )}
                    </Card>
                  </motion.div>
                );
              })}

              {/* Loose / unassigned steps. When there are no milestones, this is
                  the only section and acts as a flat step list (current behavior). */}
              {looseSteps.length > 0 && (
                <div className="space-y-2">
                  {milestones.length > 0 && (
                    <div className="text-xs text-forge-text-dim font-medium uppercase tracking-wide pt-2">
                      Other Steps
                    </div>
                  )}
                  {looseSteps.map((step) => (
                    <StepCard
                      key={step.id}
                      step={step}
                      isParent={isParent}
                      milestones={milestones}
                      onToggle={handleToggleStep}
                      onDelete={handleDeleteStep}
                      onMove={handleMoveStep}
                    />
                  ))}
                </div>
              )}

              {isParent && project.resources?.length > 0 && (
                <div className="pt-4">
                  <div className="text-xs text-forge-text-dim mb-2 font-medium uppercase tracking-wide">
                    Project-level Resources
                  </div>
                  <div className="space-y-1.5">
                    {project.resources.map((r) => (
                      <Card key={r.id} className="flex items-center justify-between py-2">
                        <ResourcePill resource={r} />
                        <button
                          onClick={() => handleDeleteResource(r.id)}
                          className="text-forge-text-dim hover:text-red-400 p-1 transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </Card>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'Materials' && (
            <div className="space-y-2">
              {isParent && (
                <button
                  onClick={() => setAddMaterialOpen(true)}
                  className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-dashed border-forge-border text-sm text-forge-text-dim hover:text-forge-text hover:border-amber-primary transition-colors"
                >
                  <Plus size={16} /> Add Material
                </button>
              )}
              {project.materials?.length > 0 && (
                <Card className="mb-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-forge-text-dim">Budget</span>
                    <span className="font-heading font-bold">${project.materials_budget}</span>
                  </div>
                  <div className="h-2 bg-forge-muted rounded-full mt-2 overflow-hidden">
                    <div
                      className="h-full bg-amber-primary rounded-full"
                      style={{
                        width: `${Math.min(100,
                          (project.materials.reduce((s, m) => s + parseFloat(m.actual_cost || m.estimated_cost || 0), 0)
                            / parseFloat(project.materials_budget || 1)) * 100
                        )}%`,
                      }}
                    />
                  </div>
                </Card>
              )}
              {project.materials?.length === 0 && (
                <EmptyState className="py-8">No materials</EmptyState>
              )}
              {project.materials?.map((mat) => (
                <Card key={mat.id} className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-sm">{mat.name}</div>
                    <div className="text-xs text-forge-text-dim">
                      Est: ${mat.estimated_cost}
                      {mat.actual_cost && ` | Actual: $${mat.actual_cost}`}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {mat.is_purchased ? (
                      <span className="text-xs text-green-400 flex items-center gap-1">
                        <Check size={14} /> Purchased
                      </span>
                    ) : (
                      <button
                        onClick={() => handleMarkPurchased(mat.id, mat.estimated_cost)}
                        className="text-xs bg-forge-muted hover:bg-forge-border px-3 py-1 rounded-lg transition-colors"
                      >
                        Mark Purchased
                      </button>
                    )}
                    {isParent && (
                      <button
                        onClick={() => handleDeleteMaterial(mat.id)}
                        className="text-forge-text-dim hover:text-red-400 p-1 transition-colors"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </Card>
              ))}
            </div>
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
            milestones={milestones}
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
          <BottomSheet title="Project QR Code" onClose={handleQrClose}>
            <div className="flex flex-col items-center gap-4">
              {qrLoading ? (
                <Loader />
              ) : qrUrl ? (
                <>
                  <img
                    src={qrUrl}
                    alt={`QR code for ${project.title}`}
                    className="w-64 h-64 rounded-lg"
                  />
                  <a
                    href={qrUrl}
                    download={`project-${id}-qr.png`}
                    className="flex items-center gap-1.5 text-sm text-amber-500 hover:underline"
                  >
                    <Download size={16} /> Save Image
                  </a>
                </>
              ) : (
                <p className="text-forge-text-dim text-sm">Failed to load QR code.</p>
              )}
            </div>
          </BottomSheet>
        )}
      </AnimatePresence>
    </div>
  );
}
