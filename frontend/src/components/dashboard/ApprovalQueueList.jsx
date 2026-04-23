import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, X, ClipboardCheck, BookOpen, Gift, Palette, Sparkles, Feather } from 'lucide-react';
import EmptyState from '../EmptyState';
import ParchmentCard from '../journal/ParchmentCard';
import RuneBadge from '../journal/RuneBadge';
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

function mutationsFor(kind) {
  if (kind === 'chore') {
    return { approve: approveChoreCompletion, reject: rejectChoreCompletion };
  }
  if (kind === 'homework') {
    return { approve: approveHomeworkSubmission, reject: rejectHomeworkSubmission };
  }
  if (kind === 'creation') {
    // Default bonus XP (15) is applied server-side when no overrides are passed.
    return {
      approve: (id) => approveCreation(id, {}),
      reject: (id) => rejectCreation(id, ''),
    };
  }
  if (kind === 'chore_proposal') {
    return { approve: null, reject: deleteChore };
  }
  if (kind === 'habit_proposal') {
    return { approve: null, reject: deleteHabit };
  }
  return { approve: approveRedemption, reject: rejectRedemption };
}

function Row({ item, onDone, onError }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(null); // 'approve' | 'reject' | null
  const [error, setError] = useState('');
  const [hidden, setHidden] = useState(false);
  const { approve, reject } = mutationsFor(item.kind);
  const meta = KIND_LABELS[item.kind] || KIND_LABELS.chore;
  const Icon = meta.icon;
  const isProposal = PROPOSAL_KINDS.has(item.kind);

  const openProposalReview = () => {
    if (item.kind === 'chore_proposal') {
      navigate('/chores');
    } else if (item.kind === 'habit_proposal') {
      navigate('/habits');
    }
  };

  const run = async (action, fn) => {
    setBusy(action);
    setError('');
    try {
      await fn(item.id);
      setHidden(true);
      setTimeout(() => onDone && onDone(item), 180);
    } catch (e) {
      setError(e?.message || 'Could not save.');
      onError && onError(e);
    } finally {
      setBusy(null);
    }
  };

  if (hidden) return null;

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
            onClick={openProposalReview}
            className="px-3 h-8 rounded-full border border-gold-leaf/70 text-gold-leaf hover:bg-gold-leaf/10 disabled:opacity-50 flex items-center justify-center font-body text-xs"
          >
            Review
          </button>
        ) : (
          <button
            type="button"
            aria-label={`Approve ${item.title}`}
            disabled={!!busy}
            onClick={() => run('approve', approve)}
            className="w-8 h-8 rounded-full border border-moss/60 text-moss hover:bg-moss/10 disabled:opacity-50 flex items-center justify-center"
          >
            <Check size={15} />
          </button>
        )}
        <button
          type="button"
          aria-label={`Reject ${item.title}`}
          disabled={!!busy}
          onClick={() => run('reject', reject)}
          className="w-8 h-8 rounded-full border border-ember/60 text-ember-deep hover:bg-ember/10 disabled:opacity-50 flex items-center justify-center"
        >
          <X size={15} />
        </button>
      </div>
    </motion.li>
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
      {groupList.map(([kidId, group]) => (
        <ParchmentCard key={kidId}>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-8 h-8 rounded-full bg-sheikah-teal/15 border border-sheikah-teal/40 flex items-center justify-center font-display text-sheikah-teal-deep text-sm">
              {group.kidName?.[0]?.toUpperCase() || '?'}
            </div>
            <div className="font-display text-base text-ink-primary truncate">
              {group.kidName}
            </div>
            <RuneBadge tone="ember" size="sm">{group.items.length}</RuneBadge>
          </div>
          <ul className="space-y-2">
            <AnimatePresence initial={false}>
              {group.items.map((it) => (
                <Row key={`${it.kind}-${it.id}`} item={it} onDone={onDone} />
              ))}
            </AnimatePresence>
          </ul>
        </ParchmentCard>
      ))}
    </section>
  );
}
