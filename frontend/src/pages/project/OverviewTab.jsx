import { ExternalLink } from 'lucide-react';
import Card from '../../components/Card';
import { ResourcePill } from './ProjectPlanItems';

export default function OverviewTab({ project, isParent }) {
  return (
    <div className="space-y-4">
      {project.description && (
        <Card><p className="text-sm">{project.description}</p></Card>
      )}
      {project.instructables_url && (
        <Card>
          <a
            href={project.instructables_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 text-amber-highlight hover:underline text-sm"
          >
            <ExternalLink size={16} /> View on Instructables
          </a>
        </Card>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card>
          <div className="text-xs text-forge-text-dim">
            {project.payment_kind === 'bounty' ? 'Bounty' : 'Bonus'}
          </div>
          <div className={`font-heading font-bold text-lg ${project.payment_kind === 'bounty' ? 'text-fuchsia-300' : ''}`}>
            ${project.bonus_amount}
          </div>
        </Card>
        <Card>
          <div className="text-xs text-forge-text-dim">Budget</div>
          <div className="font-heading font-bold text-lg">${project.materials_budget}</div>
        </Card>
        <Card>
          <div className="text-xs text-forge-text-dim">XP Reward</div>
          <div className="font-heading font-bold text-lg">{project.xp_reward}</div>
        </Card>
        <Card>
          <div className="text-xs text-forge-text-dim">Due Date</div>
          <div className="font-heading font-bold text-lg">
            {project.due_date || 'None'}
          </div>
        </Card>
      </div>

      {project.assigned_to && (
        <Card>
          <div className="text-xs text-forge-text-dim mb-1">Assigned To</div>
          <div className="text-sm font-medium">
            {project.assigned_to.display_name || project.assigned_to.username}
          </div>
          {project.hourly_rate_override && (
            <div className="text-xs text-forge-text-dim mt-1">
              Rate override: ${project.hourly_rate_override}/hr
            </div>
          )}
        </Card>
      )}

      {!project.assigned_to && project.payment_kind === 'bounty' && (
        <Card className="border-fuchsia-400/30">
          <div className="text-xs text-fuchsia-300 font-medium">Open Bounty</div>
          <div className="text-sm text-forge-text-dim mt-1">
            This bounty is available for any maker to pick up.
          </div>
        </Card>
      )}

      {isParent && project.parent_notes && (
        <Card className="border-amber-primary/30">
          <div className="text-xs text-amber-highlight mb-1 font-medium">Parent Notes</div>
          <p className="text-sm">{project.parent_notes}</p>
        </Card>
      )}

      {project.resources?.length > 0 && (
        <Card>
          <div className="text-xs text-forge-text-dim mb-2 font-medium uppercase tracking-wide">
            Resources
          </div>
          <div className="flex flex-wrap gap-2">
            {project.resources.map((r) => (
              <ResourcePill key={r.id} resource={r} />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
