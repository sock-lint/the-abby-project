import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, X, ClipboardCheck, BookOpen, Gift, Palette, Sparkles, Feather, CheckCheck } from 'lucide-react';
import EmptyState from '../EmptyState';
import ParchmentCard from '../journal/ParchmentCard';
import RuneBadge from '../journal/RuneBadge';
import BottomSheet from '../BottomSheet';
import ConfirmDialog from '../ConfirmDialog';
import Button from '../Button';
import { TextAreaField } from '../form';
import { formatCurrency } from '../../utils/format';
import {
  approveChoreCompletion, rejectChoreCompletion,
  approveHomeworkSubmission, rejectHomeworkSubmission,
  approveRedemption, rejectRedemption,
  approveCreation, rejectCreation,
  deleteChore, deleteHabit,
} from '../../api';

const KIND_LABELS = {
  chore: { label: 'duty', tone: 'moss', icon: ClipboardCheck },
  homework: { label: 'study', tone: 'royal', icon: BookOpen },
  redemption: { label: 'reward', tone: 'gold', icon: Gift },
  creation: { label: 'creation', tone: 'gold', icon: Palette },
  chore_proposal: { label: 'duty proposal', tone: 'gold', icon: Sparkles },
  habit_proposal: { label: 'ritual proposal', tone: 'royal', icon: Feather },
};

// Proposals need the parent to FILL IN rewards; we can't approve inline.
// They navigate to the owning page where the full approve modal renders.
const PROPOSAL_KINDS = new Set(['chore_proposal', 'habit_proposal']);

// Bulk-approve confirms when N exceeds this threshold (matches the plan —
// single-row stays one-tap, large fanouts get a sanity check).
const BULK_CONFIRM_THRESHOLD = 3;

function approveFor(kind) {
  if (kind === 'chore') return approveChoreCompletion;
  if (kind === 'homework') return approveHomeworkSubmission;
  if (kind === 'creation') return (id) => approveCreation(id, {});
  if (PROPOSAL_KINDS.has(kind)) return null; // not bulk-approvable
  return approveRedemption;
}

function rejectFor(kind) {
  if (kind === 'chore') return rejectChoreCompletion;
  if (kind === 'homework') return rejectHomeworkSubmission;
  if (kind === 'creation') return (id, notes) => rejectCreation(id, notes);
  if (kind === 'chore_proposal') return deleteChore;
  if (kind === 'habit_proposal') return deleteHabit;
  return rejectRedemption;
}

// Proposals don't carry a parent_notes payload — deleteChore/deleteHabit are
// destructive endpoints with no body. Everything else routes notes through.
function supportsNotes(kind) {
  return !PROPOSAL_KINDS.has(kind);
}

function rowKey(item) {
  return `${item.kind}-${item.id}`;
}

function Row({ item, isHidden, onApprove, onOpenReject, onProposalReview }) {
  const [busy, setBusy] = useState(null); // 'approve' | 'reject' | null
  const [error, setError] = useState('');
  const meta = KIND_LABELS[item.kind] || KIND_LABELS.chore;
  const Icon = meta.icon;
  const isProposal = PROPOSAL_KINDS.has(item.kind);

  if (isHidden) return null;

  const handleApprove = async () => {
    if (isProposal) {
      onProposalReview(item);
      return;
    }
    setBusy('approve');
    setError('');
    try {
      await onApprove(item);
    } catch (e) {
      setError(e?.message || 'Could not save.');
    } finally {
      setBusy(null);
    }
  };

  const handleReject = () => onOpenReject(item);

  return (
    <motion.li
      layout
      initial={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 ${error ? 'border-ember/60 bg-ember/5' : 'border-ink-page-shadow bg-ink-page'}`}
    >
      <Icon size={18} className="text-ink-secondary shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-body font-semibold text-sm truncate">{item.title}</span>
          <RuneBadge tone={meta.tone} size="sm">{meta.label}</RuneBadge>
        </div>
        {item.subtitle && (
          <div className="font-script text-xs text-ink-whisper truncate">{item.subtitle}</div>
        )}
        {error && (
          <div className="font-script text-xs text-ember-deep mt-1">{error}</div>
        )}
      </div>
      {item.reward != null && item.reward !== '' && (
        <div className="font-rune text-xs text-ember-deep pl-2 shrink-0">
          {typeof item.reward === 'number'
            ? formatCurrency(item.reward)
            : item.reward}
        </div>
      )}
      <div className="flex items-center gap-1.5 shrink-0">
        {isProposal ? (
          <button
            type="button"
            aria-label={`Review ${item.title}`}
            disabled={!!busy}
            onClick={handleApprove}
            className="px-3 h-8 rounded-full border border-gold-leaf/70 text-gold-leaf hover:bg-gold-leaf/10 disabled:opacity-50 flex items-center justify-center font-body text-xs"
          >
            Review
          </button>
        ) : (
          <button
            type="button"
            aria-label={`Approve ${item.title}`}
            disabled={!!busy}
            onClick={handleApprove}
            className="w-8 h-8 rounded-full border border-moss/60 text-moss hover:bg-moss/10 disabled:opacity-50 flex items-center justify-center"
          >
            <Check size={15} />
          </button>
        )}
        <button
          type="button"
          aria-label={`Reject ${item.title}`}
          disabled={!!busy}
          onClick={handleReject}
          className="w-8 h-8 rounded-full border border-ember/60 text-ember-deep hover:bg-ember/10 disabled:opacity-50 flex items-center justify-center"
        >
          <X size={15} />
        </button>
      </div>
    </motion.li>
  );
}

function RejectSheet({ item, onCancel, onConfirm }) {
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const showNotes = supportsNotes(item.kind);
  const isProposal = PROPOSAL_KINDS.has(item.kind);

  const submit = async (e) => {
    e?.preventDefault();
    setBusy(true);
    setError('');
    try {
      await onConfirm(item, notes.trim());
    } catch (err) {
      setError(err?.message || 'Could not reject.');
      setBusy(false);
    }
  };

  return (
    <BottomSheet
      title={isProposal ? `Delete proposal?` : `Reject "${item.title}"?`}
      onClose={busy ? undefined : onCancel}
      disabled={busy}
    >
      <form onSubmit={submit} className="space-y-3">
        {showNotes ? (
          <TextAreaField
            label="Note for the kid (optional)"
            placeholder="e.g. add a photo of the finished bed and try again"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            helpText="Shows up in their notification feed."
          />
        ) : (
          <p className="text-sm text-ink-secondary">
            This proposal will be deleted. The kid can submit a new one.
          </p>
        )}
        {error && <p className="text-sm text-ember-deep">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="px-4 py-2 text-sm text-ink-secondary hover:text-ink-primary disabled:opacity-50"
          >
            Cancel
          </button>
          <Button type="submit" variant="danger" size="sm" disabled={busy}>
            {busy ? 'Rejecting…' : (isProposal ? 'Delete' : 'Reject')}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}

/**
 * ApprovalQueueList — parent's merged pending approvals grouped by kid.
 *
 * Props:
 *   items  : unified array (see useParentDashboard shape)
 *   onDone : called after a successful approve/reject (used to reload counts)
 */
export default function ApprovalQueueList({ items = [], onDone }) {
  const navigate = useNavigate();
  const [hiddenIds, setHiddenIds] = useState(() => new Set());
  const [bulkErrors, setBulkErrors] = useState({}); // kidId -> error message
  const [bulkInFlight, setBulkInFlight] = useState(new Set());
  const [pendingBulk, setPendingBulk] = useState(null); // { kidId, group } awaiting confirm
  const [rejectTarget, setRejectTarget] = useState(null);

  const hide = (key) => {
    setHiddenIds((prev) => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
  };

  const handleApproveOne = async (item) => {
    const fn = approveFor(item.kind);
    if (!fn) return;
    await fn(item.id);
    hide(rowKey(item));
    setTimeout(() => onDone && onDone(item), 180);
  };

  const handleRejectOne = async (item, notes) => {
    const fn = rejectFor(item.kind);
    const supports = supportsNotes(item.kind);
    if (supports) {
      await fn(item.id, notes);
    } else {
      await fn(item.id);
    }
    hide(rowKey(item));
    setRejectTarget(null);
    setTimeout(() => onDone && onDone(item), 180);
  };

  const openProposalReview = (item) => {
    if (item.kind === 'chore_proposal') navigate('/chores');
    else if (item.kind === 'habit_proposal') navigate('/habits');
  };

  const runBulkApprove = async (kidId, approvable) => {
    setBulkInFlight((prev) => {
      const next = new Set(prev);
      next.add(kidId);
      return next;
    });
    setBulkErrors((prev) => {
      const next = { ...prev };
      delete next[kidId];
      return next;
    });

    // Sequential per-row optimistic hide on success; failures leave the row
    // visible. Promise.allSettled so one bad row doesn't kill the batch.
    const results = await Promise.allSettled(
      approvable.map(async (it) => {
        const fn = approveFor(it.kind);
        if (!fn) throw new Error('not approvable');
        await fn(it.id);
        return it;
      }),
    );

    let failures = 0;
    results.forEach((res, idx) => {
      if (res.status === 'fulfilled') {
        hide(rowKey(approvable[idx]));
      } else {
        failures += 1;
      }
    });

    setBulkInFlight((prev) => {
      const next = new Set(prev);
      next.delete(kidId);
      return next;
    });

    if (failures) {
      setBulkErrors((prev) => ({
        ...prev,
        [kidId]: `${failures} of ${approvable.length} could not be approved.`,
      }));
    }

    onDone && onDone();
  };

  const handleBulkClick = (kidId, group) => {
    const approvable = group.items.filter(
      (it) => !PROPOSAL_KINDS.has(it.kind) && !hiddenIds.has(rowKey(it)),
    );
    if (approvable.length === 0) return;
    if (approvable.length > BULK_CONFIRM_THRESHOLD) {
      setPendingBulk({ kidId, kidName: group.kidName, items: approvable });
    } else {
      runBulkApprove(kidId, approvable);
    }
  };

  if (!items || items.length === 0) {
    return (
      <section id="approval-queue">
        <EmptyState>
          No pending approvals. All quiet on the journal.
        </EmptyState>
      </section>
    );
  }

  const groups = items.reduce((acc, it) => {
    const key = it.kidId ?? 'unknown';
    if (!acc[key]) acc[key] = { kidName: it.kidName || 'Unassigned', items: [] };
    acc[key].items.push(it);
    return acc;
  }, {});
  const groupList = Object.entries(groups);

  return (
    <section id="approval-queue" className="space-y-3">
      {groupList.map(([kidId, group]) => {
        const visibleApprovable = group.items.filter(
          (it) => !PROPOSAL_KINDS.has(it.kind) && !hiddenIds.has(rowKey(it)),
        );
        const showBulk = visibleApprovable.length >= 2;
        const inFlight = bulkInFlight.has(kidId);
        const error = bulkErrors[kidId];
        return (
          <ParchmentCard key={kidId}>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-8 h-8 rounded-full bg-sheikah-teal/15 border border-sheikah-teal/40 flex items-center justify-center font-display text-sheikah-teal-deep text-sm">
                {group.kidName?.[0]?.toUpperCase() || '?'}
              </div>
              <div className="font-display text-base text-ink-primary truncate">
                {group.kidName}
              </div>
              <RuneBadge tone="ember" size="sm">{group.items.length}</RuneBadge>
              {showBulk && (
                <div className="ml-auto">
                  <button
                    type="button"
                    onClick={() => handleBulkClick(kidId, group)}
                    disabled={inFlight}
                    aria-label={`Approve all ${visibleApprovable.length} from ${group.kidName}`}
                    className="inline-flex items-center gap-1 px-3 h-8 rounded-full border border-moss/60 text-moss hover:bg-moss/10 disabled:opacity-50 font-body text-xs"
                  >
                    <CheckCheck size={14} />
                    {inFlight ? 'Approving…' : `Approve all (${visibleApprovable.length})`}
                  </button>
                </div>
              )}
            </div>
            {error && (
              <div role="alert" className="font-script text-xs text-ember-deep mb-2">
                {error}
              </div>
            )}
            <ul className="space-y-2">
              <AnimatePresence initial={false}>
                {group.items.map((it) => (
                  <Row
                    key={rowKey(it)}
                    item={it}
                    isHidden={hiddenIds.has(rowKey(it))}
                    onApprove={handleApproveOne}
                    onOpenReject={(target) => setRejectTarget(target)}
                    onProposalReview={openProposalReview}
                  />
                ))}
              </AnimatePresence>
            </ul>
          </ParchmentCard>
        );
      })}
      {rejectTarget && (
        <RejectSheet
          item={rejectTarget}
          onCancel={() => setRejectTarget(null)}
          onConfirm={handleRejectOne}
        />
      )}
      {pendingBulk && (
        <ConfirmDialog
          title={`Approve ${pendingBulk.items.length} for ${pendingBulk.kidName}?`}
          message={`This will mark every pending duty, study, and reward in ${pendingBulk.kidName}'s queue as approved.`}
          confirmLabel="Approve all"
          onCancel={() => setPendingBulk(null)}
          onConfirm={() => {
            const { kidId, items: pending } = pendingBulk;
            setPendingBulk(null);
            runBulkApprove(kidId, pending);
          }}
        />
      )}
    </section>
  );
}
