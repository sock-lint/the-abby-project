import { ArrowLeft, Copy, Pencil, QrCode } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { saveProjectAsTemplate } from '../../api';
import StarRating from '../../components/StarRating';
import StatusBadge from '../../components/StatusBadge';
import RuneBadge from '../../components/journal/RuneBadge';
import Button from '../../components/Button';

/**
 * Top section of ProjectDetail — back link, title/status row, and action
 * buttons (activate / submit / approve / request-changes / save-as-template /
 * edit / QR). Reskinned for the Hyrule Field Notes aesthetic.
 */
export default function ProjectHeader({
  project, isParent, isAssigned,
  onAction, onEdit, onOpenQR,
}) {
  const navigate = useNavigate();

  const handleSaveAsTemplate = async () => {
    await saveProjectAsTemplate(project.id, false);
    alert('Saved as template!');
  };

  return (
    <>
      <button
        type="button"
        onClick={() => navigate('/quests?tab=ventures')}
        className="flex items-center gap-1 font-script text-sm text-ink-whisper hover:text-ink-primary transition-colors"
      >
        <ArrowLeft size={16} /> back to ventures
      </button>

      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
        <div>
          <div className="font-script text-sheikah-teal-deep text-sm">
            venture
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            {project.title}
          </h1>
          <div className="flex items-center gap-2 mt-2 text-sm flex-wrap">
            <StatusBadge status={project.status} />
            {project.payment_kind === 'bounty' && (
              <RuneBadge tone="royal" size="sm">bounty</RuneBadge>
            )}
            {project.category && (
              <span className="font-script text-ink-whisper">
                {project.category.icon} {project.category.name}
              </span>
            )}
            <StarRating value={project.difficulty} />
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          {isParent && (project.status === 'draft' || project.status === 'active') && (
            <Button size="sm" onClick={() => onAction('activate')}>
              Activate venture
            </Button>
          )}
          {isAssigned && project.status === 'in_progress' && (
            <button
              type="button"
              onClick={() => onAction('submit')}
              className="bg-royal hover:bg-royal/85 text-ink-page-rune-glow px-4 py-2 rounded-lg text-sm font-body font-medium transition-colors border border-royal/70"
            >
              Submit for review
            </button>
          )}
          {isParent && project.status === 'in_review' && (
            <>
              <Button variant="success" size="sm" onClick={() => onAction('approve')}>
                Approve
              </Button>
              <Button variant="secondary" size="sm" onClick={() => onAction('request-changes')}>
                Request changes
              </Button>
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
        </div>
      </div>
    </>
  );
}
