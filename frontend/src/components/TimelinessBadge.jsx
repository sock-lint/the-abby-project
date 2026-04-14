const TIMELINESS_STYLES = {
  early: 'bg-moss/20 text-moss',
  on_time: 'bg-blue-500/20 text-sheikah-teal-deep',
  late: 'bg-ember/20 text-ember-deep',
  beyond_cutoff: 'bg-red-700/20 text-ember-deep',
};

const TIMELINESS_LABELS = {
  early: 'Early +25%',
  on_time: 'On Time',
  late: 'Late -50%',
  beyond_cutoff: 'Past Cutoff',
};

export default function TimelinessBadge({ timeliness }) {
  const color = TIMELINESS_STYLES[timeliness] || TIMELINESS_STYLES.on_time;
  const label = TIMELINESS_LABELS[timeliness] || timeliness;
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}
