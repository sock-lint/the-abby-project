import { ExternalLink } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import { ResourcePill } from './ProjectPlanItems';

export default function OverviewTab({ project, isParent }) {
  return (
    <div className="space-y-4">
      {project.description && (
        <ParchmentCard>
          <p className="font-body text-base text-ink-primary leading-relaxed">
            {project.description}
          </p>
        </ParchmentCard>
      )}
      {project.instructables_url && (
        <ParchmentCard>
          <a
            href={project.instructables_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 font-script text-sheikah-teal-deep hover:text-sheikah-teal text-sm transition-colors"
          >
            <ExternalLink size={16} /> view on Instructables
          </a>
        </ParchmentCard>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile
          label={project.payment_kind === 'bounty' ? 'Bounty' : 'Bonus'}
          value={`$${project.bonus_amount}`}
          tone={project.payment_kind === 'bounty' ? 'royal' : 'moss'}
        />
        <StatTile label="Budget" value={`$${project.materials_budget}`} />
        <StatTile label="XP reward" value={project.xp_reward} tone="teal" />
        <StatTile label="Due date" value={project.due_date || 'None'} />
      </div>

      {project.assigned_to && (
        <ParchmentCard>
          <div className="font-script text-xs text-ink-whisper uppercase tracking-wider mb-1">
            assigned to
          </div>
          <div className="font-body text-base font-medium text-ink-primary">
            {project.assigned_to.display_name || project.assigned_to.username}
          </div>
          {project.hourly_rate_override && (
            <div className="font-script text-xs text-ink-whisper mt-1">
              rate override: ${project.hourly_rate_override}/hr
            </div>
          )}
        </ParchmentCard>
      )}

      {!project.assigned_to && project.payment_kind === 'bounty' && (
        <ParchmentCard className="border-royal/50 bg-royal/5">
          <div className="font-script text-sm text-royal font-semibold uppercase tracking-wider">
            open bounty
          </div>
          <div className="font-body text-sm text-ink-secondary mt-1">
            This bounty is posted on the board for any adventurer to claim.
          </div>
        </ParchmentCard>
      )}

      {isParent && project.parent_notes && (
        <ParchmentCard className="border-sheikah-teal/50 bg-sheikah-teal/5">
          <div className="font-script text-xs text-sheikah-teal-deep mb-1 uppercase tracking-wider">
            keeper's notes
          </div>
          <p className="font-body text-sm text-ink-primary">{project.parent_notes}</p>
        </ParchmentCard>
      )}

      {project.resources?.length > 0 && (
        <ParchmentCard>
          <div className="font-script text-xs text-ink-whisper mb-2 uppercase tracking-wider">
            resources
          </div>
          <div className="flex flex-wrap gap-2">
            {project.resources.map((r) => (
              <ResourcePill key={r.id} resource={r} />
            ))}
          </div>
        </ParchmentCard>
      )}
    </div>
  );
}

function StatTile({ label, value, tone = 'default' }) {
  const toneClasses = {
    default: 'text-ink-primary',
    royal: 'text-royal',
    moss: 'text-moss',
    teal: 'text-sheikah-teal-deep',
  }[tone];
  return (
    <ParchmentCard>
      <div className="font-script text-xs text-ink-whisper uppercase tracking-wider">
        {label}
      </div>
      <div className={`font-display font-semibold text-lg tabular-nums ${toneClasses}`}>
        {value}
      </div>
    </ParchmentCard>
  );
}
