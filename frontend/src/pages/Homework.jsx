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
import ApprovalQueue from '../components/ApprovalQueue';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import BottomSheet from '../components/BottomSheet';
import SubjectBadge from '../components/SubjectBadge';
import StarRating from '../components/StarRating';
import TimelinessBadge from '../components/TimelinessBadge';
import ProofGallery from '../components/ProofGallery';
import StatusBadge from '../components/StatusBadge';
import ParchmentCard from '../components/journal/ParchmentCard';
import { buttonPrimary, buttonSuccess, inputClass } from '../constants/styles';
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
  const [showSubmit, setShowSubmit] = useState(null);
  const [submitImages, setSubmitImages] = useState([]);
  const [submitNotes, setSubmitNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [planning, setPlanning] = useState(null);
  const [planError, setPlanError] = useState('');

  const [form, setForm] = useState({
    title: '', description: '', subject: 'math', effort_level: 3,
    due_date: '', assigned_to: '', reward_amount: '0', coin_reward: '0',
  });

  const labelClass = 'font-script text-sm text-ink-secondary mb-1 block';

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
    setPlanError('');
    try {
      const result = await planHomework(assignment.id);
      const projectId = result?.project_id || result?.project?.id || result?.project;
      if (projectId) {
        window.location.href = `/quests/ventures/${projectId}`;
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
        </div>
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className={`${buttonPrimary} flex items-center gap-1 px-3 py-2 text-sm`}
        >
          <Plus size={14} /> New assignment
        </button>
      </header>

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
            {(a) => (
              <AssignmentCard
                key={a.id} assignment={a}
                onSubmit={() => setShowSubmit(a)}
                onPlan={() => handlePlan(a)}
                planning={planning === a.id}
                canPlan={isParent}
              />
            )}
          </Section>

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

          <Section title="Coming up" items={dashboard?.upcoming} emptyText="No upcoming assignments.">
            {(a) => (
              <AssignmentCard
                key={a.id} assignment={a}
                onSubmit={() => setShowSubmit(a)}
                onPlan={() => handlePlan(a)}
                planning={planning === a.id}
                canPlan={isParent}
              />
            )}
          </Section>
        </>
      )}

      {/* Parent view */}
      {isParent && (
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
                <div className="flex gap-1.5">
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
              <div className="flex items-center justify-between">
                <div className="font-rune text-sm text-moss tabular-nums">
                  ${sub.reward_amount_snapshot} + {sub.coin_reward_snapshot}c
                </div>
                {actions}
              </div>
            </ParchmentCard>
          )}
        </ApprovalQueue>
      )}

      {/* Create assignment */}
      {showCreate && (
        <BottomSheet onClose={() => setShowCreate(false)} title="New assignment">
          <form onSubmit={handleCreate} className="space-y-4">
            <input
              type="text" placeholder="Title" required value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className={inputClass}
            />
            <textarea
              placeholder="Description (optional)" value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              className={inputClass}
              rows={2}
            />
            <div className="grid grid-cols-2 gap-3">
              <select
                value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })}
                className={inputClass}
              >
                {SUBJECTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
              <input
                type="date" required value={form.due_date}
                onChange={(e) => setForm({ ...form, due_date: e.target.value })}
                className={inputClass}
              />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className={labelClass}>Effort (1-5)</label>
                <input
                  type="number" min={1} max={5} value={form.effort_level}
                  onChange={(e) => setForm({ ...form, effort_level: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>$ reward</label>
                <input
                  type="number" step="0.01" min={0} value={form.reward_amount}
                  onChange={(e) => setForm({ ...form, reward_amount: e.target.value })}
                  className={inputClass}
                />
              </div>
              <div>
                <label className={labelClass}>Coins</label>
                <input
                  type="number" min={0} value={form.coin_reward}
                  onChange={(e) => setForm({ ...form, coin_reward: e.target.value })}
                  className={inputClass}
                />
              </div>
            </div>
            {isParent && children.length > 0 && (
              <select
                value={form.assigned_to} required
                onChange={(e) => setForm({ ...form, assigned_to: e.target.value })}
                className={inputClass}
              >
                <option value="">Assign to…</option>
                {children.map((c) => (
                  <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
                ))}
              </select>
            )}
            <button type="submit" className={`w-full py-2.5 text-sm ${buttonPrimary}`}>
              Create assignment
            </button>
          </form>
        </BottomSheet>
      )}

      {/* Submit homework */}
      {showSubmit && (
        <BottomSheet
          onClose={() => { setShowSubmit(null); setSubmitImages([]); setSubmitNotes(''); }}
          title="Affix photographic evidence"
        >
          <div className="space-y-4">
            <div>
              <h3 className="font-display text-lg text-ink-primary">{showSubmit.title}</h3>
              <div className="flex gap-2 mt-1">
                <SubjectBadge subject={showSubmit.subject} />
                {showSubmit.timeliness_preview && (
                  <TimelinessBadge timeliness={showSubmit.timeliness_preview.timeliness} />
                )}
              </div>
            </div>

            <div>
              <label className={labelClass}>Proof photos (required)</label>
              <div className="flex gap-2 flex-wrap">
                {submitImages.map((img, i) => (
                  <div key={i} className="relative w-16 h-16 rounded-lg overflow-hidden border border-ink-page-shadow">
                    <img src={URL.createObjectURL(img)} alt="" className="w-full h-full object-cover" />
                    <button
                      type="button"
                      onClick={() => setSubmitImages(submitImages.filter((_, j) => j !== i))}
                      aria-label="Remove photo"
                      className="absolute top-0 right-0 bg-ink-primary/80 rounded-bl-lg p-0.5 text-ink-page-rune-glow"
                    >
                      <X size={12} />
                    </button>
                  </div>
                ))}
                <label className="w-16 h-16 rounded-lg border-2 border-dashed border-ink-page-shadow hover:border-sheikah-teal/60 flex items-center justify-center cursor-pointer transition-colors">
                  <Camera size={20} className="text-ink-secondary" />
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
              className={inputClass}
              rows={2}
            />

            <button
              type="button"
              onClick={handleSubmit}
              disabled={!submitImages.length || submitting}
              className={`w-full py-2.5 text-sm flex items-center justify-center gap-2 ${buttonSuccess}`}
            >
              <Send size={16} /> {submitting ? 'Submitting…' : 'Submit for review'}
            </button>
          </div>
        </BottomSheet>
      )}
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

function AssignmentCard({ assignment, onSubmit, onPlan, planning, canPlan }) {
  const a = assignment;
  const sub = a.submission_status;
  const hasProject = a.has_project;

  return (
    <ParchmentCard className="space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <SubjectBadge subject={a.subject} />
          <span className="font-display text-base text-ink-primary">{a.title}</span>
        </div>
        <div className="flex items-center gap-2">
          <StarRating value={a.effort_level} title={`Effort: ${a.effort_level}/5`} />
          {sub && <StatusBadge status={sub.status} />}
        </div>
      </div>
      <div className="flex items-center justify-between font-script text-sm text-ink-whisper">
        <span>due {a.due_date}</span>
        <span className="font-rune text-ink-secondary">
          ${a.reward_amount} + {a.coin_reward}c base
        </span>
      </div>
      <div className="flex gap-2 flex-wrap">
        {!sub && (
          <button
            type="button"
            onClick={onSubmit}
            className={`flex items-center gap-1 px-3 py-1 text-xs ${buttonSuccess}`}
          >
            <Send size={12} /> Submit
          </button>
        )}
        {!hasProject && canPlan && (
          <button
            type="button"
            onClick={onPlan}
            disabled={planning}
            className="flex items-center gap-1 px-3 py-1 bg-royal/20 hover:bg-royal/30 text-royal border border-royal/50 disabled:opacity-50 rounded-lg text-xs font-body font-medium transition-colors"
          >
            <Sparkles size={12} /> {planning ? 'Planning…' : 'Plan it out'}
          </button>
        )}
        {hasProject && (
          <a
            href={`/quests/ventures/${a.project}`}
            className="flex items-center gap-1 px-3 py-1 bg-ink-page border border-ink-page-shadow hover:border-sheikah-teal/60 rounded-lg text-xs font-body font-medium transition-colors"
          >
            <ExternalLink size={12} /> View plan
          </a>
        )}
      </div>
    </ParchmentCard>
  );
}

