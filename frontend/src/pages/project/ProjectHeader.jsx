import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Copy, Pencil, QrCode, Play } from 'lucide-react';
import { saveProjectAsTemplate } from '../../api';
import StarRating from '../../components/StarRating';
import StatusBadge from '../../components/StatusBadge';
import RuneBadge from '../../components/journal/RuneBadge';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import IlluminatedVersal from '../../components/atlas/IlluminatedVersal';
import ArtworkImage from '../../components/rpg/ArtworkImage';
import IdentitySignature from '../../components/identity/IdentitySignature';
import { tierForProgress } from '../../components/atlas/mastery.constants';
import { formatDate } from '../../utils/format';

function familyDateParts(timezone, date = new Date()) {
  return new Intl.DateTimeFormat('en-US', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(date);
}

function familyDay(timezone) {
  let parts;
  try {
    parts = familyDateParts(timezone);
  } catch {
    parts = familyDateParts('UTC');
  }
  const part = (name) => parts.find((value) => value.type === name).value;
  return `${part('year')}-${part('month')}-${part('day')}`;
}

function completionTime(value, timezone) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return null;
  const options = { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' };
  try {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: timezone }).format(date);
  } catch {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: 'UTC' }).format(date);
  }
}

// Status → workflow-progress percent. Drives the gilt fill on the project's
// drop-cap so a draft glimmers faintly, in_review reads three-quarters
// inked, and completed projects sit fully gilded with a halo. Archived
// projects keep the gilt because the work was done — they're past tense,
// not unfinished.
const STATUS_PROGRESS = {
  draft: 5,
  active: 25,
  in_progress: 55,
  in_review: 80,
  completed: 100,
  archived: 100,
};

function projectVersalProps(project) {
  const progressPct = STATUS_PROGRESS[project.status] ?? 25;
  const unlocked = project.status !== 'draft';
  return {
    progressPct,
    tier: tierForProgress({ unlocked, progressPct, level: 0, maxLevel: 6 }),
  };
}

/**
 * Top section of ProjectDetail — back link, title/status row, and action
 * buttons (activate / submit / approve / request-changes / save-as-template /
 * edit / QR). Reskinned for the Hyrule Field Notes aesthetic.
 */
export default function ProjectHeader({
  project, isParent, isAssigned, personal = false,
  onAction, onEdit, onOpenQR, timezone = 'America/Phoenix',
}) {
  const navigate = useNavigate();
  const isHomeworkPlan = project.is_homework_plan;
  const recordedCompletion = completionTime(project.completed_at, timezone);
  const duePassed = ['draft', 'active', 'in_progress'].includes(project.status)
    && project.due_date && project.due_date < familyDay(timezone);
  const [flash, setFlash] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(''), 3000);
    return () => clearTimeout(t);
  }, [flash]);

  const handleSaveAsTemplate = async () => {
    setError('');
    try {
      await saveProjectAsTemplate(project.id, false);
      setFlash('Saved as template.');
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <>
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <IlluminatedVersal
            letter={project.title?.charAt(0) || '✦'}
            size="lg"
            {...projectVersalProps(project)}
          />
          <div className="min-w-0 flex-1">
            <div className="font-script text-sheikah-teal-deep text-body">
              {isHomeworkPlan ? 'Homework plan' : 'project'}
            </div>
            <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
              {project.title}
            </h1>
            <div className="flex items-center gap-2 mt-2 text-body flex-wrap">
              {!isHomeworkPlan && <StatusBadge status={project.status} />}
              {!isHomeworkPlan && project.payment_kind === 'bounty' && (
                <RuneBadge tone="royal" size="sm">optional project</RuneBadge>
              )}
              {project.category && (
                <span className="font-script text-ink-whisper">
                  <ArtworkImage assetId={project.category.catalog_icon} fallback={project.category.icon || null} size={20} /> {project.category.name}
                </span>
              )}
              <StarRating value={project.difficulty} />
            </div>
            {!isHomeworkPlan && <div className="mt-3 space-y-1 font-body text-caption text-ink-secondary">
              {project.due_date
                ? <p>{['completed', 'archived'].includes(project.status) ? 'Current due' : 'Due'} <time dateTime={project.due_date}>{formatDate(project.due_date)}</time></p>
                : <p>No due date set</p>}
              {duePassed && <p>Due date passed</p>}
              {recordedCompletion
                ? <p>{['completed', 'archived'].includes(project.status) ? 'Completion recorded' : 'Previous completion recorded'} <time dateTime={project.completed_at}>{recordedCompletion}</time></p>
                : project.status === 'completed' && <p>Completion date unavailable</p>}
              {project.status === 'in_review' && <p>Awaiting completion approval</p>}
            </div>}
            {!isHomeworkPlan && project.maker_signature && <section aria-label="Project maker" className="mt-4">
              <IdentitySignature identity={project.maker_signature}
                prefix={project.status === 'completed' || (project.status === 'archived' && project.completed_at) ? 'Made by' : 'Project by'} portraitSize="sm" />
            </section>}
          </div>
        </div>
        {!isHomeworkPlan && <div className="flex gap-2 flex-wrap">
          {(!isParent || personal) && isAssigned && ['active', 'in_progress'].includes(project.status) && (
            <Button
              size="sm"
              onClick={() => navigate(`/clock?project=${project.id}`)}
              className="flex items-center gap-1"
            >
              <Play size={14} aria-hidden="true" /> Work on this project
            </Button>
          )}
          {isParent && (project.status === 'draft' || project.status === 'active') && (
            <Button size="sm" onClick={() => onAction('activate')}>
              Start project
            </Button>
          )}
          {isAssigned && project.status === 'in_progress' && !personal && (
            // Royal tone marks the child's one hand-off action apart from the
            // parent's teal actions beside it; the `!` overrides ride on the
            // Button primitive so height, disabled and focus behavior stay in
            // lockstep with its size="sm" siblings in this row.
            <Button
              size="sm"
              onClick={() => onAction('submit')}
              className="!bg-royal hover:!bg-royal/85 !border-royal/70 !text-ink-page-rune-glow"
            >
              Submit for review
            </Button>
          )}
          {personal && isAssigned && project.status === 'in_progress' && <Button variant="success" size="sm" onClick={() => onAction('approve')}>Complete project</Button>}
          {isParent && project.status === 'in_review' && (
            <>
              <Button variant="success" size="sm" onClick={() => onAction('approve')}>
                {personal ? 'Complete project' : 'Approve'}
              </Button>
              {!personal && <Button variant="secondary" size="sm" onClick={() => onAction('request-changes')}>
                Request changes
              </Button>}
            </>
          )}
          {isParent && project.status === 'completed' && (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleSaveAsTemplate}
              className="flex items-center gap-1"
            >
              <Copy size={14} /> Save as template
            </Button>
          )}
          {isParent && (
            <Button
              variant="secondary"
              size="sm"
              onClick={onEdit}
              className="flex items-center gap-1"
            >
              <Pencil size={14} /> Edit
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={onOpenQR}
            className="flex items-center gap-1"
          >
            <QrCode size={14} /> QR
          </Button>
        </div>}
      </div>

      {flash && (
        <div
          role="status"
          className="text-body px-3 py-2 rounded-lg bg-sheikah-teal-deep/10 text-sheikah-teal-deep border border-sheikah-teal-deep/30 font-body"
        >
          {flash}
        </div>
      )}
      <ErrorAlert message={error} />
    </>
  );
}
