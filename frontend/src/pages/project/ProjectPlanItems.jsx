import { motion } from 'framer-motion';
import {
  Check, Trash2, Video, FileText, Image as ImageIcon, Link as LinkIcon,
} from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';

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
      className="inline-flex items-center gap-1.5 text-xs bg-ink-page-aged hover:bg-ink-page-rune-glow text-ink-primary px-2.5 py-1 rounded-full border border-ink-page-shadow hover:border-sheikah-teal/50 transition-colors font-body"
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
      <ParchmentCard className={step.is_completed ? 'opacity-60' : ''}>
        <div className="flex items-start gap-3">
          <button
            type="button"
            onClick={() => onToggle(step)}
            aria-label={step.is_completed ? 'Uncheck step' : 'Mark step complete'}
            className={`w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0 mt-0.5 transition-all ${
              step.is_completed
                ? 'bg-moss border-moss'
                : 'border-ink-page-shadow hover:border-sheikah-teal-deep hover:bg-sheikah-teal/15'
            }`}
          >
            {step.is_completed && <Check size={14} className="text-ink-page-rune-glow" strokeWidth={3} />}
          </button>
          <div className="flex-1 min-w-0">
            <div className={`font-body font-medium text-sm text-ink-primary ${step.is_completed ? 'line-through' : ''}`}>
              {step.title}
            </div>
            {step.description && (
              <div className="font-body text-xs text-ink-secondary mt-1 whitespace-pre-wrap">
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
                <span className="font-script text-[11px] text-ink-whisper uppercase tracking-wider">
                  move to
                </span>
                <select
                  value={step.milestone ?? ''}
                  onChange={(e) => onMove(step, e.target.value)}
                  className="text-xs bg-ink-page border border-ink-page-shadow rounded px-1.5 py-0.5 text-ink-primary font-body focus:outline-none focus:border-sheikah-teal"
                >
                  <option value="">(no milestone)</option>
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
              type="button"
              onClick={() => onDelete(step.id)}
              aria-label="Delete step"
              className="text-ink-secondary hover:text-ember-deep p-1 transition-colors shrink-0"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </ParchmentCard>
    </motion.div>
  );
}
