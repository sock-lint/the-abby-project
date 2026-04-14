import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Send, Camera, X, ExternalLink, Sparkles } from 'lucide-react';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import {
  getHomeworkDashboard, createHomework,
  submitHomework, approveHomeworkSubmission,
  rejectHomeworkSubmission, planHomework, getChildren,
} from '../api';
import Card from '../components/Card';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import EmptyState from '../components/EmptyState';
import BottomSheet from '../components/BottomSheet';
import SubjectBadge from '../components/SubjectBadge';
import StarRating from '../components/StarRating';
import TimelinessBadge from '../components/TimelinessBadge';
import ProofGallery from '../components/ProofGallery';
import StatusBadge from '../components/StatusBadge';
import { downscaleImage } from '../utils/image';

const SUBJECTS = [
  { value: 'math', label: 'Math' },
  { value: 'reading', label: 'Reading' },
  { value: 'writing', label: 'Writing' },
  { value: 'science', label: 'Science' },
  { value: 'social_studies', label: 'Social Studies' },
  { value: 'art', label: 'Art' },
  { value: 'music', label: 'Music' },
  { value: 'other', label: 'Other' },
];

export default function Homework() {
  const { isParent } = useRole();

  const { data: dashboard, loading, error, reload } = useApi(getHomeworkDashboard);
  const { data: childrenData } = useApi(isParent ? getChildren : null);
  const children = childrenData || [];

  const [showCreate, setShowCreate] = useState(false);
  const [showSubmit, setShowSubmit] = useState(null); // assignment object
  const [submitImages, setSubmitImages] = useState([]);
  const [submitNotes, setSubmitNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [planning, setPlanning] = useState(null); // assignment id

  // Create form state
  const [form, setForm] = useState({
    title: '', description: '', subject: 'math', effort_level: 3,
    due_date: '', assigned_to: '', reward_amount: '0', coin_reward: '0',
  });

  const handleCreate = async (e) => {
    e.preventDefault();
    await createHomework({
      ...form,
      effort_level: parseInt(form.effort_level),
      reward_amount: form.reward_amount,
      coin_reward: parseInt(form.coin_reward),
      assigned_to: isParent ? parseInt(form.assigned_to) : undefined,
    });
    setShowCreate(false);
    setForm({ title: '', description: '', subject: 'math', effort_level: 3, due_date: '', assigned_to: '', reward_amount: '0', coin_reward: '0' });
    reload();
  };

  const handleSubmit = async () => {
    if (!submitImages.length || !showSubmit) return;
    setSubmitting(true);
    try {
      const downscaled = await Promise.all(submitImages.map((img) => downscaleImage(img)));
      const fd = new FormData();
      downscaled.forEach((img) => fd.append('images', img));
      if (submitNotes) fd.append('notes', submitNotes);
      await submitHomework(showSubmit.id, fd);
      setShowSubmit(null);
      setSubmitImages([]);
      setSubmitNotes('');
      reload();
    } finally {
      setSubmitting(false);
    }
  };

  const handleApprove = async (id) => {
    await approveHomeworkSubmission(id);
    reload();
  };

  const handleReject = async (id) => {
    await rejectHomeworkSubmission(id);
    reload();
  };

  const handlePlan = async (assignment) => {
    setPlanning(assignment.id);
    try {
      const result = await planHomework(assignment.id);
      if (result?.project_id) {
        window.location.href = `/projects/${result.project_id}`;
      }
    } catch {
      // AI planning not yet available
    } finally {
      setPlanning(null);
      reload();
    }
  };

  if (loading) return <Loader />;
  if (error) return <ErrorAlert message={error} />;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Homework</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} /> New
        </button>
      </div>

      {/* Child Dashboard View */}
      {!isParent && (
        <>
          {/* Overdue banner */}
          {dashboard?.overdue?.length > 0 && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
              {dashboard.overdue.length} overdue assignment{dashboard.overdue.length > 1 ? 's' : ''}
            </div>
          )}

          {/* Stats strip */}
          {dashboard?.stats && (
            <div className="grid grid-cols-3 gap-3">
              <Card className="text-center py-3">
                <div className="text-2xl font-bold">{dashboard.stats.completion_rate}%</div>
                <div className="text-xs text-white/50">Completion</div>
              </Card>
              <Card className="text-center py-3">
                <div className="text-2xl font-bold">{dashboard.stats.on_time_rate}%</div>
                <div className="text-xs text-white/50">On Time</div>
              </Card>
              <Card className="text-center py-3">
                <div className="text-2xl font-bold">{dashboard.stats.total_approved}</div>
                <div className="text-xs text-white/50">Completed</div>
              </Card>
            </div>
          )}

          {/* Today's homework */}
          <Section title="Due Today" items={dashboard?.today} emptyText="Nothing due today!">
            {(a) => (
              <AssignmentCard
                key={a.id} assignment={a}
                onSubmit={() => setShowSubmit(a)}
                onPlan={() => handlePlan(a)}
                planning={planning === a.id}
              />
            )}
          </Section>

          {/* Overdue */}
          {dashboard?.overdue?.length > 0 && (
            <Section title="Overdue" items={dashboard.overdue}>
              {(a) => (
                <AssignmentCard
                  key={a.id} assignment={a}
                  onSubmit={() => setShowSubmit(a)}
                  onPlan={() => handlePlan(a)}
                  planning={planning === a.id}
                />
              )}
            </Section>
          )}

          {/* Upcoming */}
          <Section title="Coming Up" items={dashboard?.upcoming} emptyText="No upcoming homework.">
            {(a) => (
              <AssignmentCard
                key={a.id} assignment={a}
                onSubmit={() => setShowSubmit(a)}
                onPlan={() => handlePlan(a)}
                planning={planning === a.id}
              />
            )}
          </Section>
        </>
      )}

      {/* Parent View */}
      {isParent && (
        <>
          {/* Pending approvals */}
          <Section title="Pending Approval" items={dashboard?.pending_submissions} emptyText="No pending submissions.">
            {(sub) => (
              <Card key={sub.id} className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-medium">{sub.user_name}</span>
                    <span className="text-white/50 mx-2">&mdash;</span>
                    <span>{sub.assignment_title}</span>
                  </div>
                  <div className="flex gap-1.5">
                    <TimelinessBadge timeliness={sub.timeliness} />
                    <StatusBadge status={sub.status} />
                  </div>
                </div>
                {sub.notes && <p className="text-sm text-white/60">{sub.notes}</p>}
                <ProofGallery proofs={sub.proofs} />
                <div className="text-sm text-white/50">
                  ${sub.reward_amount_snapshot} + {sub.coin_reward_snapshot}c
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleApprove(sub.id)}
                    className="px-3 py-1.5 bg-green-600 hover:bg-green-500 rounded-lg text-sm font-medium transition-colors"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => handleReject(sub.id)}
                    className="px-3 py-1.5 bg-red-600/50 hover:bg-red-500/50 rounded-lg text-sm font-medium transition-colors"
                  >
                    Reject
                  </button>
                </div>
              </Card>
            )}
          </Section>
        </>
      )}

      {/* Create Assignment Sheet */}
      <BottomSheet open={showCreate} onClose={() => setShowCreate(false)} title="New Homework">
        <form onSubmit={handleCreate} className="space-y-4">
          <input
            type="text" placeholder="Title" required value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm"
          />
          <textarea
            placeholder="Description (optional)" value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm"
            rows={2}
          />
          <div className="grid grid-cols-2 gap-3">
            <select
              value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm"
            >
              {SUBJECTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
            <input
              type="date" required value={form.due_date}
              onChange={(e) => setForm({ ...form, due_date: e.target.value })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm"
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-xs text-white/50 block mb-1">Effort (1-5)</label>
              <input
                type="number" min={1} max={5} value={form.effort_level}
                onChange={(e) => setForm({ ...form, effort_level: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-white/50 block mb-1">$ Reward</label>
              <input
                type="number" step="0.01" min={0} value={form.reward_amount}
                onChange={(e) => setForm({ ...form, reward_amount: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="text-xs text-white/50 block mb-1">Coins</label>
              <input
                type="number" min={0} value={form.coin_reward}
                onChange={(e) => setForm({ ...form, coin_reward: e.target.value })}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>
          {isParent && children.length > 0 && (
            <select
              value={form.assigned_to} required
              onChange={(e) => setForm({ ...form, assigned_to: e.target.value })}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm"
            >
              <option value="">Assign to...</option>
              {children.map((c) => (
                <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
              ))}
            </select>
          )}
          <button type="submit" className="w-full bg-blue-600 hover:bg-blue-500 rounded-lg py-2 text-sm font-medium transition-colors">
            Create Assignment
          </button>
        </form>
      </BottomSheet>

      {/* Submit Homework Sheet */}
      <BottomSheet open={!!showSubmit} onClose={() => { setShowSubmit(null); setSubmitImages([]); setSubmitNotes(''); }} title="Submit Homework">
        {showSubmit && (
          <div className="space-y-4">
            <div>
              <h3 className="font-medium">{showSubmit.title}</h3>
              <div className="flex gap-2 mt-1">
                <SubjectBadge subject={showSubmit.subject} />
                {showSubmit.timeliness_preview && (
                  <TimelinessBadge timeliness={showSubmit.timeliness_preview.timeliness} />
                )}
              </div>
            </div>

            {/* Image picker */}
            <div>
              <label className="text-xs text-white/50 block mb-2">Proof photos (required)</label>
              <div className="flex gap-2 flex-wrap">
                {submitImages.map((img, i) => (
                  <div key={i} className="relative w-16 h-16 rounded-lg overflow-hidden border border-white/10">
                    <img src={URL.createObjectURL(img)} alt="" className="w-full h-full object-cover" />
                    <button
                      onClick={() => setSubmitImages(submitImages.filter((_, j) => j !== i))}
                      className="absolute top-0 right-0 bg-black/70 rounded-bl-lg p-0.5"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
                <label className="w-16 h-16 rounded-lg border border-dashed border-white/20 flex items-center justify-center cursor-pointer hover:border-white/40 transition-colors">
                  <Camera size={20} className="text-white/40" />
                  <input
                    type="file" accept="image/*" multiple className="hidden"
                    onChange={(e) => setSubmitImages([...submitImages, ...Array.from(e.target.files)])}
                  />
                </label>
              </div>
            </div>

            <textarea
              placeholder="Notes (optional)" value={submitNotes}
              onChange={(e) => setSubmitNotes(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm"
              rows={2}
            />

            <button
              onClick={handleSubmit}
              disabled={!submitImages.length || submitting}
              className="w-full bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg py-2 text-sm font-medium transition-colors flex items-center justify-center gap-2"
            >
              <Send size={16} /> {submitting ? 'Submitting...' : 'Submit for Review'}
            </button>
          </div>
        )}
      </BottomSheet>
    </div>
  );
}

function Section({ title, items, emptyText, children }) {
  return (
    <div>
      <h2 className="text-sm font-semibold text-white/50 uppercase tracking-wide mb-2">{title}</h2>
      {!items?.length ? (
        emptyText && <p className="text-sm text-white/30">{emptyText}</p>
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
    </div>
  );
}

function AssignmentCard({ assignment, onSubmit, onPlan, planning }) {
  const a = assignment;
  const sub = a.submission_status;
  const hasProject = a.has_project;

  return (
    <Card className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <SubjectBadge subject={a.subject} />
          <span className="font-medium">{a.title}</span>
        </div>
        <div className="flex items-center gap-2">
          <StarRating value={a.effort_level} title={`Effort: ${a.effort_level}/5`} />
          {sub && <StatusBadge status={sub.status} />}
        </div>
      </div>
      <div className="flex items-center justify-between text-sm text-white/50">
        <span>Due {a.due_date}</span>
        <span>
          ${a.reward_amount} + {a.coin_reward}c base
        </span>
      </div>
      <div className="flex gap-2">
        {!sub && (
          <button
            onClick={onSubmit}
            className="flex items-center gap-1 px-3 py-1 bg-green-600/80 hover:bg-green-500 rounded-lg text-xs font-medium transition-colors"
          >
            <Send size={12} /> Submit
          </button>
        )}
        {!hasProject && (
          <button
            onClick={onPlan}
            disabled={planning}
            className="flex items-center gap-1 px-3 py-1 bg-purple-600/80 hover:bg-purple-500 disabled:opacity-50 rounded-lg text-xs font-medium transition-colors"
          >
            <Sparkles size={12} /> {planning ? 'Planning...' : 'Plan This Out'}
          </button>
        )}
        {hasProject && (
          <a
            href={`/projects/${a.project}`}
            className="flex items-center gap-1 px-3 py-1 bg-white/5 hover:bg-white/10 rounded-lg text-xs font-medium transition-colors"
          >
            <ExternalLink size={12} /> View Plan
          </a>
        )}
      </div>
    </Card>
  );
}
