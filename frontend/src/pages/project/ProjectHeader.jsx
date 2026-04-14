import { ArrowLeft, Copy, Pencil, QrCode } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { saveProjectAsTemplate } from '../../api';
import StarRating from '../../components/StarRating';
import StatusBadge from '../../components/StatusBadge';
import { buttonPrimary, buttonSecondary, buttonSuccess } from '../../constants/styles';

/**
 * Top section of ProjectDetail: back link, title/status row, and the action
 * buttons (activate/submit/approve/request-changes/save-as-template/edit/QR).
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
        onClick={() => navigate('/projects')}
        className="flex items-center gap-1 text-sm text-forge-text-dim hover:text-forge-text"
      >
        <ArrowLeft size={16} /> Back to Projects
      </button>

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="font-heading text-2xl font-bold">{project.title}</h1>
          <div className="flex items-center gap-3 mt-1 text-sm text-forge-text-dim">
            <StatusBadge status={project.status} />
            {project.payment_kind === 'bounty' && (
              <span className="text-[10px] font-bold uppercase tracking-wide px-2 py-0.5 rounded bg-fuchsia-400/15 text-fuchsia-300 border border-fuchsia-400/30">
                Bounty
              </span>
            )}
            {project.category && <span>{project.category.icon} {project.category.name}</span>}
            <StarRating value={project.difficulty} />
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          {isParent && (project.status === 'draft' || project.status === 'active') && (
            <button onClick={() => onAction('activate')} className={`px-4 py-2 text-sm ${buttonPrimary}`}>
              Activate Project
            </button>
          )}
          {isAssigned && project.status === 'in_progress' && (
            <button
              onClick={() => onAction('submit')}
              className="bg-purple-600 hover:bg-purple-500 text-white px-4 py-2 rounded-lg text-sm font-medium"
            >
              Submit for Review
            </button>
          )}
          {isParent && project.status === 'in_review' && (
            <>
              <button
                onClick={() => onAction('approve')}
                className={`px-4 py-2 text-sm ${buttonSuccess}`}
              >
                Approve
              </button>
              <button
                onClick={() => onAction('request-changes')}
                className={`px-4 py-2 text-sm ${buttonSecondary}`}
              >
                Request Changes
              </button>
            </>
          )}
          {isParent && project.status === 'completed' && (
            <button
              onClick={handleSaveAsTemplate}
              className={`flex items-center gap-1 px-4 py-2 text-sm ${buttonSecondary}`}
            >
              <Copy size={14} /> Save as Template
            </button>
          )}
          {isParent && (
            <button
              onClick={onEdit}
              className={`flex items-center gap-1 px-3 py-2 text-sm ${buttonSecondary}`}
            >
              <Pencil size={14} /> Edit
            </button>
          )}
          <button
            onClick={onOpenQR}
            className={`flex items-center gap-1 px-3 py-2 text-sm ${buttonSecondary}`}
          >
            <QrCode size={14} /> QR
          </button>
        </div>
      </div>
    </>
  );
}
