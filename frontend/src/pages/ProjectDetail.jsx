import { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Check, ChevronDown, ExternalLink, ArrowLeft, DollarSign, QrCode, Copy,
  Pencil, Plus, Trash2, Video, FileText, Image as ImageIcon, Link as LinkIcon,
  Download,
} from 'lucide-react';
import {
  getProject, updateProject, submitProject, approveProject, requestChanges,
  completeMilestone, createMilestone, deleteMilestone,
  markPurchased, createMaterial, deleteMaterial,
  saveProjectAsTemplate, activateProject, getCategories, getChildren,
  completeStep, uncompleteStep, createStep, updateStep, deleteStep,
  createResource, deleteResource, getProjectQR,
} from '../api';
import { useApi } from '../hooks/useApi';
import BottomSheet from '../components/BottomSheet';
import Card from '../components/Card';
import DifficultyStars from '../components/DifficultyStars';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
import ProgressBar from '../components/ProgressBar';
import StatusBadge from '../components/StatusBadge';
import { inputClass } from '../constants/styles';
import { normalizeList } from '../utils/api';

const tabs = ['Overview', 'Plan', 'Materials'];

const LOOSE_KEY = '__loose__';

const RESOURCE_ICONS = {
  video: Video,
  doc: FileText,
  image: ImageIcon,
  link: LinkIcon,
};

function ResourcePill({ resource }) {
  const Icon = RESOURCE_ICONS[resource.resource_type] || LinkIcon;
  return (
    <a
      href={resource.url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 text-xs bg-forge-muted hover:bg-forge-border text-forge-text px-2.5 py-1 rounded-full border border-forge-border transition-colors"
    >
      <Icon size={12} />
      <span className="truncate max-w-[180px]">{resource.title || resource.url}</span>
    </a>
  );
}

function StepCard({
  step, isParent, milestones, onToggle, onDelete, onMove,
}) {
  return (
    <motion.div layout>
      <Card className={step.is_completed ? 'opacity-60' : ''}>
        <div className="flex items-start gap-3">
          <button
            onClick={() => onToggle(step)}
            className={`w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0 mt-0.5 transition-colors ${
              step.is_completed
                ? 'bg-green-500 border-green-500'
                : 'border-forge-muted hover:border-amber-primary'
            }`}
          >
            {step.is_completed && <Check size={14} className="text-white" />}
          </button>
          <div className="flex-1 min-w-0">
            <div className={`font-medium text-sm ${step.is_completed ? 'line-through' : ''}`}>
              {step.title}
            </div>
            {step.description && (
              <div className="text-xs text-forge-text-dim mt-1 whitespace-pre-wrap">
                {step.description}
              </div>
            )}
            {step.resources?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {step.resources.map((r) => (
                  <ResourcePill key={r.id} resource={r} />
                ))}
              </div>
            )}
            {isParent && milestones.length > 0 && (
              <div className="mt-2 flex items-center gap-1.5">
                <span className="text-[10px] uppercase tracking-wide text-forge-text-dim">
                  Move to
                </span>
                <select
                  value={step.milestone ?? ''}
                  onChange={(e) => onMove(step, e.target.value)}
                  className="text-xs bg-forge-bg border border-forge-border rounded px-1.5 py-0.5 text-forge-text"
                >
                  <option value="">(No milestone)</option>
                  {milestones.map((m, idx) => (
                    <option key={m.id} value={m.id}>
                      {idx + 1}. {(m.title || `Milestone ${idx + 1}`).slice(0, 30)}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          {isParent && (
            <button
              onClick={() => onDelete(step.id)}
              className="text-forge-text-dim hover:text-red-400 p-1 transition-colors shrink-0"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </Card>
    </motion.div>
  );
}

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
            <DifficultyStars difficulty={project.difficulty} />
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

/* ── Edit Project Modal ─────────────────────────────────────────── */

function EditProjectModal({ project, onClose, onSaved }) {
  const { data: categoriesData } = useApi(getCategories);
  const { data: childrenData } = useApi(getChildren);
  const categories = normalizeList(categoriesData);
  const children = normalizeList(childrenData);

  const [form, setForm] = useState({
    title: project.title || '',
    description: project.description || '',
    difficulty: project.difficulty || 2,
    category_id: project.category?.id || '',
    assigned_to_id: project.assigned_to?.id || '',
    bonus_amount: project.bonus_amount || '0',
    payment_kind: project.payment_kind || 'required',
    hourly_rate_override: project.hourly_rate_override || '',
    materials_budget: project.materials_budget || '0',
    due_date: project.due_date || '',
    parent_notes: project.parent_notes || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await updateProject(project.id, {
        ...form,
        difficulty: parseInt(form.difficulty),
        category_id: form.category_id || null,
        assigned_to_id: form.assigned_to_id || null,
        hourly_rate_override: form.hourly_rate_override || null,
        due_date: form.due_date || null,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Edit Project" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Title</label>
          <input value={form.title} onChange={set('title')} className={inputClass} required />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Description</label>
          <textarea value={form.description} onChange={set('description')} className={`${inputClass} h-20 resize-none`} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Category</label>
            <select value={form.category_id} onChange={set('category_id')} className={inputClass}>
              <option value="">None</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Difficulty</label>
            <select value={form.difficulty} onChange={set('difficulty')} className={inputClass}>
              {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>)}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Assign To</label>
            <select value={form.assigned_to_id} onChange={set('assigned_to_id')} className={inputClass}>
              <option value="">Unassigned</option>
              {children.map((c) => (
                <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Payment Kind</label>
            <select value={form.payment_kind} onChange={set('payment_kind')} className={inputClass}>
              <option value="required">Required</option>
              <option value="bounty">Bounty</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">
              {form.payment_kind === 'bounty' ? 'Bounty ($)' : 'Bonus ($)'}
            </label>
            <input value={form.bonus_amount} onChange={set('bonus_amount')} className={inputClass} type="number" step="0.01" min="0" />
          </div>
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Budget ($)</label>
            <input value={form.materials_budget} onChange={set('materials_budget')} className={inputClass} type="number" step="0.01" min="0" />
          </div>
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Rate Override ($)</label>
            <input value={form.hourly_rate_override} onChange={set('hourly_rate_override')} className={inputClass} type="number" step="0.01" min="0" placeholder="Default" />
          </div>
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Due Date</label>
          <input value={form.due_date} onChange={set('due_date')} className={inputClass} type="date" />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Parent Notes</label>
          <textarea value={form.parent_notes} onChange={set('parent_notes')} className={`${inputClass} h-16 resize-none`} placeholder="Private notes" />
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

/* ── Add Milestone Modal ────────────────────────────────────────── */

function AddMilestoneModal({ projectId, onClose, onSaved }) {
  const [form, setForm] = useState({ title: '', description: '', bonus_amount: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await createMilestone(projectId, {
        project: projectId,
        title: form.title,
        description: form.description,
        bonus_amount: form.bonus_amount || null,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Milestone" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Title</label>
          <input value={form.title} onChange={set('title')} className={inputClass} required autoFocus />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Description</label>
          <textarea value={form.description} onChange={set('description')} className={`${inputClass} h-16 resize-none`} />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Bonus ($)</label>
          <input value={form.bonus_amount} onChange={set('bonus_amount')} className={inputClass} type="number" step="0.01" min="0" placeholder="Optional" />
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.title.trim()} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Adding...' : 'Add Milestone'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

/* ── Add Material Modal ─────────────────────────────────────────── */

function AddMaterialModal({ projectId, onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', description: '', estimated_cost: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await createMaterial(projectId, {
        project: projectId,
        name: form.name,
        description: form.description,
        estimated_cost: form.estimated_cost || '0',
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Material" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Name</label>
          <input value={form.name} onChange={set('name')} className={inputClass} required autoFocus />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Description</label>
          <textarea value={form.description} onChange={set('description')} className={`${inputClass} h-16 resize-none`} />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Estimated Cost ($)</label>
          <input value={form.estimated_cost} onChange={set('estimated_cost')} className={inputClass} type="number" step="0.01" min="0" />
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.name.trim()} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Adding...' : 'Add Material'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

/* ── Add Step Modal ─────────────────────────────────────────────── */

function AddStepModal({ projectId, milestones = [], initialMilestoneId = null, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: '',
    description: '',
    milestone: initialMilestoneId == null ? '' : String(initialMilestoneId),
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await createStep(projectId, {
        project: projectId,
        title: form.title,
        description: form.description,
        milestone: form.milestone === '' ? null : Number(form.milestone),
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Step" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <p className="text-xs text-forge-text-dim">
          Steps are walkthrough instructions — no coins, XP, or ledger impact.
        </p>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Title</label>
          <input value={form.title} onChange={set('title')} className={inputClass} required autoFocus />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Description</label>
          <textarea
            value={form.description}
            onChange={set('description')}
            className={`${inputClass} h-24 resize-none`}
            placeholder="What does the maker do next?"
          />
        </div>
        {milestones.length > 0 && (
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Milestone</label>
            <select value={form.milestone} onChange={set('milestone')} className={inputClass}>
              <option value="">(No milestone — loose step)</option>
              {milestones.map((m, idx) => (
                <option key={m.id} value={m.id}>
                  {idx + 1}. {m.title || `Milestone ${idx + 1}`}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.title.trim()} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Adding...' : 'Add Step'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

/* ── Add Resource Modal ─────────────────────────────────────────── */

function AddResourceModal({ projectId, steps, onClose, onSaved }) {
  const [form, setForm] = useState({
    title: '',
    url: '',
    resource_type: 'link',
    step: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await createResource(projectId, {
        project: projectId,
        title: form.title,
        url: form.url,
        resource_type: form.resource_type,
        step: form.step || null,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Resource" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">URL</label>
          <input
            value={form.url}
            onChange={set('url')}
            className={inputClass}
            type="url"
            placeholder="https://..."
            required
            autoFocus
          />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Title (optional)</label>
          <input value={form.title} onChange={set('title')} className={inputClass} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Type</label>
            <select value={form.resource_type} onChange={set('resource_type')} className={inputClass}>
              <option value="link">Link</option>
              <option value="video">Video</option>
              <option value="doc">Document</option>
              <option value="image">Image</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Attach to Step</label>
            <select value={form.step} onChange={set('step')} className={inputClass}>
              <option value="">(Project-level)</option>
              {steps.map((s, idx) => (
                <option key={s.id} value={s.id}>
                  {idx + 1}. {s.title.slice(0, 40)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.url.trim()} className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 text-black font-semibold py-3 rounded-lg transition-colors">
            {saving ? 'Adding...' : 'Add Resource'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

/* ── Request Changes Modal ──────────────────────────────────────── */

function RequestChangesModal({ onClose, onSubmit }) {
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!notes.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit(notes.trim());
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <BottomSheet title="Request Changes" onClose={onClose} disabled={submitting}>
      <p className="text-sm text-forge-text-dim">
        Tell the maker what needs to change before you approve this project.
      </p>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="What should they fix or add?"
        autoFocus
        rows={4}
        className="w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text text-base resize-none focus:outline-none focus:border-amber-primary"
      />
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onClose}
          disabled={submitting}
          className="flex-1 bg-forge-muted hover:bg-forge-border text-forge-text font-medium py-3 rounded-lg transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={submitting || !notes.trim()}
          className="flex-1 bg-amber-primary hover:bg-amber-highlight disabled:opacity-50 disabled:cursor-not-allowed text-black font-semibold py-3 rounded-lg transition-colors"
        >
          {submitting ? 'Sending...' : 'Send'}
        </button>
      </div>
    </BottomSheet>
  );
}

