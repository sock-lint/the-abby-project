import { motion } from 'framer-motion';
import {
  Check, Trash2, Video, FileText, Image as ImageIcon, Link as LinkIcon,
} from 'lucide-react';
import Card from '../../components/Card';

const RESOURCE_ICONS = {
  video: Video,
  doc: FileText,
  image: ImageIcon,
  link: LinkIcon,
};

export function ResourcePill({ resource }) {
  const Icon = RESOURCE_ICONS[resource.resource_type] || LinkIcon;
  return (
    <a
      href={resource.url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 text-xs bg-forge-muted hover:bg-forge-border text-forge-text px-2.5 py-1 rounded-full border border-forge-border transition-colors"
    >
      <Icon size={12} />
      <span className="truncate max-w-[180px]">{resource.title || resource.url}</span>
    </a>
  );
}

export function StepCard({
  step, isParent, milestones, onToggle, onDelete, onMove,
}) {
  return (
    <motion.div layout>
      <Card className={step.is_completed ? 'opacity-60' : ''}>
        <div className="flex items-start gap-3">
          <button
            onClick={() => onToggle(step)}
            className={`w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0 mt-0.5 transition-colors ${
              step.is_completed
                ? 'bg-green-500 border-green-500'
                : 'border-forge-muted hover:border-amber-primary'
            }`}
          >
            {step.is_completed && <Check size={14} className="text-white" />}
          </button>
          <div className="flex-1 min-w-0">
            <div className={`font-medium text-sm ${step.is_completed ? 'line-through' : ''}`}>
              {step.title}
            </div>
            {step.description && (
              <div className="text-xs text-forge-text-dim mt-1 whitespace-pre-wrap">
                {step.description}
              </div>
            )}
            {step.resources?.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {step.resources.map((r) => (
                  <ResourcePill key={r.id} resource={r} />
                ))}
              </div>
            )}
            {isParent && milestones.length > 0 && (
              <div className="mt-2 flex items-center gap-1.5">
                <span className="text-[10px] uppercase tracking-wide text-forge-text-dim">
                  Move to
                </span>
                <select
                  value={step.milestone ?? ''}
                  onChange={(e) => onMove(step, e.target.value)}
                  className="text-xs bg-forge-bg border border-forge-border rounded px-1.5 py-0.5 text-forge-text"
                >
                  <option value="">(No milestone)</option>
                  {milestones.map((m, idx) => (
                    <option key={m.id} value={m.id}>
                      {idx + 1}. {(m.title || `Milestone ${idx + 1}`).slice(0, 30)}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          {isParent && (
            <button
              onClick={() => onDelete(step.id)}
              className="text-forge-text-dim hover:text-red-400 p-1 transition-colors shrink-0"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </Card>
    </motion.div>
  );
}
