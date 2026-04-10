import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, ExternalLink, ArrowLeft, DollarSign, QrCode, Copy, X } from 'lucide-react';
import { getProject, submitProject, approveProject, requestChanges, completeMilestone, markPurchased, saveProjectAsTemplate, activateProject } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import StatusBadge from '../components/StatusBadge';
import Loader from '../components/Loader';

const tabs = ['Overview', 'Milestones', 'Materials'];

export default function ProjectDetail({ user }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data: project, loading, reload } = useApi(() => getProject(id), [id]);
  const [activeTab, setActiveTab] = useState('Overview');
  const [changesOpen, setChangesOpen] = useState(false);

  if (loading) return <Loader />;
  if (!project) return <div className="text-forge-text-dim">Project not found</div>;

  const isParent = user?.role === 'parent';
  const isAssigned = project.assigned_to?.id === user?.id;

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
                🎯 Bounty
              </span>
            )}
            {project.category && <span>{project.category.icon} {project.category.name}</span>}
            <span>{'★'.repeat(project.difficulty)}{'☆'.repeat(5 - project.difficulty)}</span>
          </div>
        </div>
        <div className="flex gap-2">
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
          <a
            href={`/api/projects/${id}/qr/`}
            target="_blank"
            rel="noopener noreferrer"
            className="bg-forge-muted hover:bg-forge-border text-forge-text px-3 py-2 rounded-lg text-sm font-medium flex items-center gap-1"
          >
            <QrCode size={14} /> QR
          </a>
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
              {isParent && project.parent_notes && (
                <Card className="border-amber-primary/30">
                  <div className="text-xs text-amber-highlight mb-1 font-medium">Parent Notes</div>
                  <p className="text-sm">{project.parent_notes}</p>
                </Card>
              )}
            </div>
          )}

          {activeTab === 'Milestones' && (
            <div className="space-y-2">
              {project.milestones?.length === 0 && (
                <Card className="text-center py-8 text-forge-text-dim">No milestones</Card>
              )}
              {project.milestones?.map((ms) => (
                <motion.div key={ms.id} layout>
                  <Card className={`flex items-center gap-3 ${ms.is_completed ? 'opacity-60' : ''}`}>
                    <button
                      onClick={() => !ms.is_completed && handleCompleteMilestone(ms.id)}
                      disabled={ms.is_completed}
                      className={`w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors ${
                        ms.is_completed
                          ? 'bg-green-500 border-green-500'
                          : 'border-forge-muted hover:border-amber-primary'
                      }`}
                    >
                      {ms.is_completed && <Check size={14} className="text-white" />}
                    </button>
                    <div className="flex-1">
                      <div className={`font-medium text-sm ${ms.is_completed ? 'line-through' : ''}`}>
                        {ms.title}
                      </div>
                      {ms.description && <div className="text-xs text-forge-text-dim">{ms.description}</div>}
                    </div>
                    {ms.bonus_amount && (
                      <span className="text-xs text-green-400 flex items-center gap-0.5">
                        <DollarSign size={12} />{ms.bonus_amount}
                      </span>
                    )}
                  </Card>
                </motion.div>
              ))}
            </div>
          )}

          {activeTab === 'Materials' && (
            <div className="space-y-2">
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
                <Card className="text-center py-8 text-forge-text-dim">No materials</Card>
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
      </AnimatePresence>
    </div>
  );
}

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
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={submitting ? undefined : onClose}
        className="fixed inset-0 bg-black/60 z-40"
      />
      <motion.div
        initial={{ y: '100%' }}
        animate={{ y: 0 }}
        exit={{ y: '100%' }}
        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        className="fixed bottom-0 left-0 right-0 bg-forge-card border-t border-forge-border rounded-t-2xl z-50 pb-[env(safe-area-inset-bottom)] md:left-1/2 md:right-auto md:bottom-auto md:top-1/2 md:-translate-x-1/2 md:-translate-y-1/2 md:w-full md:max-w-md md:rounded-2xl md:border"
      >
        <div className="flex justify-center pt-2 md:hidden">
          <div className="w-10 h-1 rounded-full bg-forge-muted" />
        </div>
        <div className="flex items-center justify-between px-4 pt-3 pb-2">
          <h2 className="font-heading text-lg font-bold">Request Changes</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            aria-label="Close"
            className="text-forge-text-dim hover:text-forge-text min-h-10 min-w-10 flex items-center justify-center rounded-lg"
          >
            <X size={20} />
          </button>
        </div>
        <div className="px-4 pb-4 space-y-3">
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
              {submitting ? 'Sending…' : 'Send'}
            </button>
          </div>
        </div>
      </motion.div>
    </>
  );
}
