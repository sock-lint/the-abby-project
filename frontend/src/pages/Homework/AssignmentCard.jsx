import { Send, ExternalLink, Sparkles } from 'lucide-react';
import SubjectBadge from '../../components/SubjectBadge';
import StarRating from '../../components/StarRating';
import StatusBadge from '../../components/StatusBadge';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';

export default function AssignmentCard({ assignment, onSubmit, onPlan, planning, canPlan }) {
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
      <div className="font-script text-sm text-ink-whisper">
        due {a.due_date}
      </div>
      <div className="flex gap-2 flex-wrap">
        {!sub && (
          <Button
            variant="success"
            size="sm"
            onClick={onSubmit}
            className="flex items-center gap-1 text-xs"
          >
            <Send size={12} /> Submit
          </Button>
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
