import { Link } from 'react-router-dom';
import { Send, ExternalLink, Sparkles, Pencil, Trash2, Undo2 } from 'lucide-react';
import SubjectBadge from '../../components/SubjectBadge';
import StarRating from '../../components/StarRating';
import StatusBadge from '../../components/StatusBadge';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import { formatDate } from '../../utils/format';

export default function AssignmentCard({
  assignment, onSubmit, onPlan, planning, canPlan,
  canManage, onEdit, onDelete, onWithdraw,
}) {
  const a = assignment;
  const sub = a.submission_status;
  const hasProject = a.has_project;
  const canWithdraw = sub && sub.status === 'pending' && typeof onWithdraw === 'function';

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
      <div className="font-script text-body text-ink-whisper">
        due {formatDate(a.due_date)}
      </div>
      <div className="flex gap-2 flex-wrap items-center">
        {!sub && (
          <Button
            variant="success"
            size="sm"
            onClick={onSubmit}
            className="flex items-center gap-1"
          >
            <Send size={14} /> Submit
          </Button>
        )}
        {canWithdraw && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onWithdraw(sub.id)}
            title="Pull this submission back so you can re-photo or re-submit"
            className="flex items-center gap-1"
          >
            <Undo2 size={14} /> Withdraw
          </Button>
        )}
        {!hasProject && canPlan && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onPlan}
            disabled={planning}
            title="turn this assignment into a planned venture with steps and materials"
            className="flex items-center gap-1"
          >
            <Sparkles size={14} /> {planning ? 'Planning…' : 'Plan it out'}
          </Button>
        )}
        {hasProject && (
          // Client-side transition. A raw <a> tore the installed PWA down to
          // the splash screen and refetched every dashboard call on the way
          // back in.
          <Link
            to={`/quests/ventures/${a.project}`}
            className="inline-flex items-center gap-1 min-h-11 px-3 py-1 bg-ink-page-aged hover:bg-ink-page-shadow border border-ink-page-shadow rounded-lg text-body font-body font-medium text-ink-primary transition-colors"
          >
            <ExternalLink size={14} /> View plan
          </Link>
        )}
        {canManage && (
          <div className="flex gap-1 ml-auto">
            <IconButton
              variant="secondary"
              onClick={onEdit}
              aria-label="Edit assignment"
            >
              <Pencil size={16} />
            </IconButton>
            <IconButton
              variant="danger"
              onClick={onDelete}
              aria-label="Delete assignment"
            >
              <Trash2 size={16} />
            </IconButton>
          </div>
        )}
      </div>
    </ParchmentCard>
  );
}
