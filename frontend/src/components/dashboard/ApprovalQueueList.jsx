import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, X, ClipboardCheck, BookOpen, Gift, Palette, Sparkles, Feather, CheckCheck } from 'lucide-react';
import { CoinIcon } from '../icons/JournalIcons';
import EmptyState from '../EmptyState';
import ParchmentSkeleton from '../ParchmentSkeleton';
import ParchmentCard from '../journal/ParchmentCard';
import RuneBadge from '../journal/RuneBadge';
import BottomSheet from '../BottomSheet';
import ProofGallery from '../ProofGallery';
import ConfirmDialog from '../ConfirmDialog';
import Button from '../Button';
import ModalActions from '../ModalActions';
import { TextAreaField, SelectField } from '../form';
import CheckboxField from '../form/CheckboxField';
import { formatCurrency } from '../../utils/format';
import {
  approveChoreCompletion, rejectChoreCompletion,
  approveHomeworkSubmission, rejectHomeworkSubmission,
  approveRedemption, rejectRedemption,
  approveCreation, rejectCreation,
  approveExchange, rejectExchange,
  deleteChore, deleteHabit,
} from '../../api';

const KIND_LABELS = {
  chore: { label: 'chore', tone: 'moss', icon: ClipboardCheck },
  homework: { label: 'homework', tone: 'royal', icon: BookOpen },
  redemption: { label: 'reward', tone: 'gold', icon: Gift },
  creation: { label: 'creation', tone: 'gold', icon: Palette },
  chore_proposal: { label: 'chore proposal', tone: 'gold', icon: Sparkles },
  habit_proposal: { label: 'habit proposal', tone: 'royal', icon: Feather },
  exchange: { label: 'exchange', tone: 'ember', icon: CoinIcon },
};

// Proposals need the parent to FILL IN rewards; we can't approve inline.
// They navigate to the owning page where the full approve modal renders.
const PROPOSAL_KINDS = new Set(['chore_proposal', 'habit_proposal']);

// Bulk-approve confirms when N exceeds this threshold (matches the plan —
// single-row stays one-tap, large fanouts get a sanity check).
function waitingLabel(value) {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return null;
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60000));
  if (minutes < 60) return `Waiting ${minutes}m`;
  if (minutes < 1440) return `Waiting ${Math.floor(minutes / 60)}h`;
  return `Waiting ${Math.floor(minutes / 1440)}d`;
}

function approvalSummary(items) {
  const kinds = new Set(items.map((item) => item.kind));
  const notes = [];
  if (kinds.has('chore') || kinds.has('homework') || kinds.has('creation')) notes.push('Completed work receives its configured rewards.');
  if (kinds.has('redemption')) notes.push('Reward requests use their held coins; real-world rewards still need delivery.');
  if (kinds.has('exchange')) notes.push('Money exchanges deduct money owed and credit coins.');
  return `${items.map((item) => item.title).join('; ')}. ${notes.join(' ')}`;
}

function approveFor(kind) {
  if (kind === 'chore') return approveChoreCompletion;
  if (kind === 'homework') return approveHomeworkSubmission;
  if (kind === 'creation') return (id) => approveCreation(id, {});
  if (kind === 'exchange') return approveExchange;
  if (PROPOSAL_KINDS.has(kind)) return null; // not bulk-approvable
  return approveRedemption;
}

function rejectFor(kind) {
  if (kind === 'chore') return rejectChoreCompletion;
  if (kind === 'homework') return rejectHomeworkSubmission;
  if (kind === 'creation') return (id, notes) => rejectCreation(id, notes);
  if (kind === 'exchange') return rejectExchange;
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

// First photo a kid attached to this submission, if any.
function thumbFor(item) {
  return item.image || item.proofs?.[0]?.image || null;
}

function hasDetail(item) {
  return Boolean(thumbFor(item) || item.notes);
}

function Row({ item, isHidden, onApprove, onOpenReject, onProposalReview, onOpenDetail, selected, onSelect, groupBusy }) {
  const [busy, setBusy] = useState(null); // 'approve' | 'reject' | null
  const [error, setError] = useState('');
  const meta = KIND_LABELS[item.kind] || KIND_LABELS.chore;
  const Icon = meta.icon;
  const isProposal = PROPOSAL_KINDS.has(item.kind);
  const waiting = waitingLabel(item.submittedAt);

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
      exit={{ opacity: 0, x: 60, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className={`flex flex-col gap-3 rounded-xl border px-3 py-2.5 sm:flex-row sm:items-center ${error ? 'border-ember/60 bg-ember/5' : 'border-ink-page-shadow bg-ink-page'}`}
    >
      <div className="flex min-w-0 flex-1 items-start gap-3 sm:items-center">
        {!isProposal && <CheckboxField labelNode={<span className="sr-only">Select {item.title} from {item.kidName}</span>}
          checked={selected} disabled={!!busy || groupBusy} onChange={onSelect} />}
        {thumbFor(item) ? (
          <img
            src={thumbFor(item)}
            alt=""
            loading="lazy"
            decoding="async"
            className="w-11 h-11 rounded-lg object-cover border border-ink-page-shadow shrink-0"
          />
        ) : (
          <Icon size={18} className="text-ink-secondary shrink-0" />
        )}
        {/* The body is a button when there's evidence to inspect — approving
            homework or a creation from a one-line title alone is approving
            blind, and the photo is already in the payload. */}
        {hasDetail(item) ? (
          <button
            type="button"
            onClick={() => onOpenDetail(item)}
            className="flex-1 min-w-0 text-left"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-body font-semibold text-body break-words [overflow-wrap:anywhere]">{item.title}</span>
              <RuneBadge tone={meta.tone} size="sm">{meta.label}</RuneBadge>
            </div>
            {item.subtitle && (
              <div className="font-script text-caption text-ink-whisper break-words">{item.subtitle}</div>
            )}
            <div className="font-script text-caption text-sheikah-teal-deep">
              tap to see the work
            </div>
            {error && (
              <div className="font-script text-caption text-ember-deep mt-1 break-words">{error}</div>
            )}
          </button>
        ) : (
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-body font-semibold text-body break-words [overflow-wrap:anywhere]">{item.title}</span>
              <RuneBadge tone={meta.tone} size="sm">{meta.label}</RuneBadge>
            </div>
            {item.subtitle && (
              <div className="font-script text-caption text-ink-whisper break-words">{item.subtitle}</div>
            )}
            {error && (
              <div className="font-script text-caption text-ember-deep mt-1 break-words">{error}</div>
            )}
          </div>
        )}
      </div>
      <div className="flex min-w-0 items-center justify-end gap-3 sm:shrink-0">
        {waiting && <span className="text-caption text-ink-secondary">{waiting}</span>}
        {item.reward != null && item.reward !== '' && (
          <div className="mr-auto min-w-0 font-rune text-caption text-ember-deep break-words sm:mr-0 sm:pl-2">
            {Number.isFinite(Number(item.reward))
              ? formatCurrency(item.reward)
              : item.reward}
          </div>
        )}
        {/* 44px circles with real spacing — parents triage this queue
            one-handed, and approve/reject sitting 6px apart at 32px was the
            classic wrong-button mis-tap. Mirrors ApprovalButtons' 44px floor. */}
        <div className="flex items-center gap-3 shrink-0">
          {isProposal ? (
            <button
              type="button"
              aria-label={`Review ${item.title}`}
              disabled={!!busy || groupBusy}
              onClick={handleApprove}
              className="px-3 h-11 rounded-full border border-gold-leaf/70 text-gold-leaf hover:bg-gold-leaf/10 disabled:opacity-50 flex items-center justify-center font-body text-caption"
            >
              Review
            </button>
          ) : (
            <button
              type="button"
              aria-label={`Approve ${item.title}`}
              disabled={!!busy || groupBusy}
              onClick={handleApprove}
              className="w-11 h-11 rounded-full border border-moss/60 text-moss hover:bg-moss/10 disabled:opacity-50 flex items-center justify-center"
            >
              <Check size={18} />
            </button>
          )}
          <button
            type="button"
            aria-label={`Reject ${item.title}`}
            disabled={!!busy || groupBusy}
            onClick={handleReject}
            className="w-11 h-11 rounded-full border border-ember/60 text-ember-deep hover:bg-ember/10 disabled:opacity-50 flex items-center justify-center"
          >
            <X size={18} />
          </button>
        </div>
      </div>
    </motion.li>
  );
}

function DetailSheet({ item, onClose, onApprove, onReject }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const meta = KIND_LABELS[item.kind] || KIND_LABELS.chore;
  const photos = item.proofs?.length
    ? item.proofs
    : (item.image ? [{ id: 'image', image: item.image, caption: null }] : []);

  // A rejected approve MUST surface here and keep the sheet open — this is the
  // flow where the parent inspected the photo before deciding, and a silent
  // return to "Approve" reads as "it worked". Mirrors the inline Row's catch.
  const handleApprove = async () => {
    setBusy(true);
    setError('');
    try {
      await onApprove(item);
      onClose();
    } catch (e) {
      setError(e?.message || 'Could not save.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <BottomSheet title={item.title} onClose={onClose} disabled={busy}>
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <RuneBadge tone={meta.tone} size="sm">{meta.label}</RuneBadge>
          <span className="font-script text-caption text-ink-whisper">
            {item.kidName}
            {item.subtitle ? ` · ${item.subtitle}` : ''}
          </span>
        </div>
        {photos.length > 0 && (
          <ProofGallery proofs={photos} />
        )}
        {item.notes && (
          <p className="font-body text-body text-ink-secondary whitespace-pre-line">
            {item.notes}
          </p>
        )}
        {error && (
          <p role="alert" className="font-script text-body text-ember-deep">
            {error}
          </p>
        )}
        {/* Reject left, Approve right — same order as the forge approval
            sheet and ModalActions, so a parent moving between the two
            queues isn't re-learning which half is which. */}
        <div className="flex gap-2 pt-1">
          <Button
            variant="danger"
            onClick={() => { onClose(); onReject(item); }}
            disabled={busy}
            className="flex-1"
          >
            Reject
          </Button>
          <Button
            variant="success"
            onClick={handleApprove}
            disabled={busy}
            className="flex-1"
          >
            {busy ? 'Approving…' : 'Approve'}
          </Button>
        </div>
      </div>
    </BottomSheet>
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
          <p className="text-body text-ink-secondary">
            This proposal will be deleted. The kid can submit a new one.
          </p>
        )}
        {error && <p className="text-body text-ember-deep">{error}</p>}
        <ModalActions
          onClose={onCancel}
          submitVariant="danger"
          submitLabel={isProposal ? 'Delete' : 'Reject'}
          savingLabel={isProposal ? 'Deleting…' : 'Rejecting…'}
          saving={busy}
        />
      </form>
    </BottomSheet>
  );
}

/**
 * ApprovalQueueList — parent's merged pending approvals grouped by kid.
 *
 * Props:
 *   items   : unified array (see useParentDashboard shape)
 *   loading : true while the first aggregate is still in flight. Renders a
 *             skeleton instead of the "all quiet" empty state — an empty
 *             array means "nothing pending" ONLY once the fetches resolve.
 *   incomplete : an approval source failed, so an empty result is unverified
 *   showEmpty : false when the parent already shows other attention items
 *   onDone  : called after a successful approve/reject (used to reload counts)
 */
export default function ApprovalQueueList({
  items = [], loading = false, incomplete = false, showEmpty = true, onDone,
}) {
  const navigate = useNavigate();
  const [hiddenIds, setHiddenIds] = useState(() => new Set());
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [sortOrder, setSortOrder] = useState('oldest');
  const [bulkErrors, setBulkErrors] = useState({}); // kidId -> error message
  const [bulkInFlight, setBulkInFlight] = useState(new Set());
  const [pendingBulk, setPendingBulk] = useState(null); // { kidId, group } awaiting confirm
  const [rejectTarget, setRejectTarget] = useState(null);
  const [detailTarget, setDetailTarget] = useState(null);
  const mounted = useRef(false);
  const refreshTimers = useRef(new Set());

  useEffect(() => {
    mounted.current = true;
    const timers = refreshTimers.current;
    return () => {
      mounted.current = false;
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
    };
  }, []);

  const scheduleRefresh = (item) => {
    if (!mounted.current) return;
    // Each successful row keeps its animation delay and completion callback.
    const timer = setTimeout(() => {
      refreshTimers.current.delete(timer);
      if (mounted.current) onDone && onDone(item);
    }, 180);
    refreshTimers.current.add(timer);
  };

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
    if (!mounted.current) return;
    hide(rowKey(item));
    scheduleRefresh(item);
  };

  const handleRejectOne = async (item, notes) => {
    const fn = rejectFor(item.kind);
    const supports = supportsNotes(item.kind);
    if (supports) {
      await fn(item.id, notes);
    } else {
      await fn(item.id);
    }
    if (!mounted.current) return;
    hide(rowKey(item));
    setRejectTarget(null);
    scheduleRefresh(item);
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
    if (!mounted.current) return;

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

  const toggleSelected = (key) => setSelectedIds((previous) => {
    const next = new Set(previous);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });

  const handleBulkClick = (kidId, group) => {
    const approvable = group.items.filter((item) => selectedIds.has(rowKey(item))
      && !PROPOSAL_KINDS.has(item.kind) && !hiddenIds.has(rowKey(item)));
    if (approvable.length) setPendingBulk({ kidId, kidName: group.kidName, items: approvable });
  };

  if (!items || items.length === 0) {
    if (!loading && !showEmpty) return null;
    return (
      <section>
        {loading ? (
          <ParchmentSkeleton variant="list" count={3} />
        ) : (
          <EmptyState>
            {incomplete ? "Some approval queues couldn't be checked. Try again above."
              : 'No pending approvals.'}
          </EmptyState>
        )}
      </section>
    );
  }

  const ordered = [...items].sort((left, right) => {
    const a = Date.parse(left.submittedAt);
    const b = Date.parse(right.submittedAt);
    if (!Number.isFinite(a)) return Number.isFinite(b) ? 1 : 0;
    if (!Number.isFinite(b)) return -1;
    return sortOrder === 'oldest' ? a - b : b - a;
  });
  const groups = ordered.reduce((acc, it) => {
    const key = it.kidId ?? 'unknown';
    if (!acc[key]) acc[key] = { kidName: it.kidName || 'Unassigned', items: [] };
    acc[key].items.push(it);
    return acc;
  }, {});
  const groupList = Object.entries(groups);

  return (
    <section className="space-y-3">
      <SelectField label="Review order" value={sortOrder} onChange={(event) => setSortOrder(event.target.value)} className="sm:max-w-xs">
        <option value="oldest">Oldest first</option><option value="newest">Newest first</option>
      </SelectField>
      {groupList.map(([kidId, group]) => {
        const visibleApprovable = group.items.filter(
          (it) => !PROPOSAL_KINDS.has(it.kind) && !hiddenIds.has(rowKey(it)),
        );
        const selected = visibleApprovable.filter((item) => selectedIds.has(rowKey(item)));
        const showBulk = visibleApprovable.length >= 2 || selected.length > 0;
        const allSelected = visibleApprovable.length > 0 && selected.length === visibleApprovable.length;
        const inFlight = bulkInFlight.has(kidId);
        const error = bulkErrors[kidId];
        return (
          <ParchmentCard key={kidId}>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <div className="w-8 h-8 shrink-0 rounded-full bg-sheikah-teal/15 border border-sheikah-teal/40 flex items-center justify-center font-display text-sheikah-teal-deep text-body">
                {group.kidName?.[0]?.toUpperCase() || '?'}
              </div>
              <div className="min-w-0 font-display text-base text-ink-primary break-words [overflow-wrap:anywhere]">
                {group.kidName}
              </div>
              <RuneBadge tone="ember" size="sm">{group.items.filter((item) => !hiddenIds.has(rowKey(item))).length}</RuneBadge>
              {showBulk && (
                <div className="ml-auto flex flex-wrap gap-2">
                  <Button variant="ghost" size="sm" disabled={inFlight}
                    onClick={() => setSelectedIds((previous) => {
                      const next = new Set(previous);
                      visibleApprovable.forEach((item) => { if (allSelected) next.delete(rowKey(item)); else next.add(rowKey(item)); });
                      return next;
                    })}>{allSelected ? 'Clear selection' : `Select all from ${group.kidName}`}</Button>
                  <button
                    type="button"
                    onClick={() => handleBulkClick(kidId, group)}
                    disabled={inFlight || selected.length === 0}
                    aria-label={`Approve selected ${selected.length} from ${group.kidName}`}
                    className="inline-flex items-center gap-1 px-3 h-11 rounded-full border border-moss/60 text-moss hover:bg-moss/10 disabled:opacity-50 font-body text-caption"
                  >
                    <CheckCheck size={14} />
                    {inFlight ? 'Approving…' : `Approve selected (${selected.length})`}
                  </button>
                </div>
              )}
            </div>
            {error && (
              <div role="alert" className="font-script text-caption text-ember-deep mb-2">
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
                    onOpenDetail={(target) => setDetailTarget(target)}
                    selected={selectedIds.has(rowKey(it))}
                    onSelect={() => toggleSelected(rowKey(it))}
                    groupBusy={inFlight}
                  />
                ))}
              </AnimatePresence>
            </ul>
          </ParchmentCard>
        );
      })}
      {detailTarget && (
        <DetailSheet
          item={detailTarget}
          onClose={() => setDetailTarget(null)}
          onApprove={handleApproveOne}
          onReject={(target) => setRejectTarget(target)}
        />
      )}
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
          message={approvalSummary(pendingBulk.items)}
          confirmLabel="Approve selected"
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
