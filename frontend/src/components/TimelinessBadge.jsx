const TIMELINESS_STYLES = {
  early: 'bg-moss/20 text-moss',
  on_time: 'bg-blue-500/20 text-sheikah-teal-deep',
  late: 'bg-ember/20 text-ember-deep',
  beyond_cutoff: 'bg-red-700/20 text-ember-deep',
};

const TIMELINESS_LABELS = {
  early: 'Early',
  on_time: 'On time',
  late: 'Late',
  beyond_cutoff: 'Late',
};

export default function TimelinessBadge({ timeliness }) {
  const known = Object.hasOwn(TIMELINESS_LABELS, timeliness);
  const color = known ? TIMELINESS_STYLES[timeliness] : 'bg-ink-page-shadow/40 text-ink-secondary';
  const label = known ? TIMELINESS_LABELS[timeliness] : 'Timing unknown';
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-caption font-medium ${color}`}>
      {label}
    </span>
  );
}
