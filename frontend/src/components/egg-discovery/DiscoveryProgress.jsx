import ProgressBar from '../ProgressBar';

const TYPES = [['reading', 'Reading or listening'], ['movement', 'Movement'], ['practice', 'Making or practice']];

export function DiscoveryRequirements({ requirements }) {
  if (!requirements) return null;
  const rare = requirements.guaranteed_search != null;
  return <div className="space-y-1 text-caption text-ink-secondary">
    {rare ? <>
      <p>Each search uses {requirements.minutes_per_search} minutes of activity, with at most {requirements.max_minutes_per_type_per_search} minutes from one activity type. Mix two or three types.</p>
      <p>{requirements.chance_percent}% chance on each of the first {requirements.guaranteed_search - 1} searches. Search {requirements.guaranteed_search} guarantees this egg if you have not found it sooner.</p>
      <p>All {requirements.guaranteed_search} searches together use {requirements.minutes_per_search * requirements.guaranteed_search} minutes of varied activity. Extra time in just one activity waits for more variety.</p>
    </> : <p>{requirements.total_minutes} minutes total, including at least {requirements.min_minutes_per_type} minutes in each of {requirements.activity_types_required} activity types.</p>}
    {requirements.required_hatched_species > 0 && <p>Available after hatching {requirements.required_hatched_species} different companion species.</p>}
  </div>;
}

export default function DiscoveryProgress({ discovery, compact = false }) {
  const requirements = discovery.requirements || {};
  const rare = requirements.guaranteed_search != null;
  const total = TYPES.reduce((sum, [type]) => sum + (discovery.minutes?.[type] || 0), 0);
  const searches = discovery.searches || [];
  const pending = discovery.delivery_pending === true;
  const completed = discovery.status === 'completed' && !pending;
  return <div className="space-y-3">
    {pending ? <div className="space-y-1" role="status">
      <p className="font-semibold text-body text-ink-primary">Activity saved. Your discovery is complete, but its egg and supplies have not been delivered yet.</p>
      <p className="text-caption text-ink-secondary">No more activity is needed for this egg. Your result stays saved.</p>
    </div> : completed ? <p className="font-semibold text-body text-moss-deep">Egg earned</p> : rare ? <>
      <p className="text-body text-ink-primary">{searches.length} of {requirements.guaranteed_search} searches completed</p>
      <ProgressBar value={searches.length} max={requirements.guaranteed_search} aria-label={`${discovery.name} searches`} />
      <p className="text-caption text-ink-secondary">At most {discovery.remaining_searches} more {discovery.remaining_searches === 1 ? 'search' : 'searches'} until you find this egg.</p>
    </> : <>
      <p className="text-body text-ink-primary">{total} of {requirements.total_minutes} minutes recorded</p>
      <ProgressBar value={total} max={requirements.total_minutes} aria-label={`${discovery.name} activity minutes`} />
      <p className="text-caption text-ink-secondary">Include at least {requirements.min_minutes_per_type} minutes in each of {requirements.activity_types_required} activity types.</p>
    </>}
    {!compact && !completed && <>
      <p className="text-caption font-semibold text-ink-primary">Your recorded activity</p>
      <dl className="grid gap-1 text-caption text-ink-secondary">
        {TYPES.map(([type, label]) => <div key={type} className="flex flex-wrap justify-between gap-2"><dt>{label}</dt><dd>{discovery.minutes?.[type] || 0} minutes</dd></div>)}
      </dl>
    </>}
    {!compact && <DiscoveryRequirements requirements={requirements} />}
    {!compact && searches.length > 0 && <ol className="space-y-1 text-caption text-ink-secondary" aria-label="Saved search results">
      {searches.map((search) => <li key={search.number}>Search {search.number}: {search.found ? pending ? 'Discovery complete — delivery pending' : search.guaranteed ? 'Egg found — guaranteed discovery' : 'Egg found' : 'No egg found — counts toward your guarantee'}</li>)}
    </ol>}
  </div>;
}
