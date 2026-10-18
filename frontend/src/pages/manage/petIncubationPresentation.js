export function isSupportedIncubationPolicy(policy) {
  return policy && Number.isSafeInteger(policy.duration_seconds) && policy.duration_seconds >= 0
    && policy.max_active === 1 && policy.clock === 'elapsed_seconds'
    && policy.start_strategy === 'first_compatible_pair_during_care'
    && policy.claim_strategy === 'next_active_care_visit_at_or_after_ready';
}

export function formatIncubationWait(seconds) {
  if (!Number.isSafeInteger(seconds) || seconds < 0) return 'Unrecorded';
  if (seconds === 0) return '0 seconds';
  return [[Math.floor(seconds / 3600), 'hour'], [Math.floor((seconds % 3600) / 60), 'minute'], [seconds % 60, 'second']]
    .filter(([value]) => value > 0)
    .map(([value, unit]) => `${value} ${unit}${value === 1 ? '' : 's'}`).join(' ');
}
