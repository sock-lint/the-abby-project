import { useEffect, useState } from 'react';

/**
 * Drives a phase counter through a list of timed milestones via setTimeout.
 * Pass an array of phase durations in ms; the hook returns the current
 * phase index (0..N). Phase 0 is the initial mount; each subsequent
 * phase begins after the previous duration elapses. The terminal index
 * is ``phases.length``, which is the "sequence complete" signal.
 *
 * If ``reduced`` is true the hook jumps straight to the terminal phase
 * so callers branch their reduced-motion fallback off the same return
 * value used for the normal animation.
 *
 * Re-runs only when the serialized phase array changes — callers pass
 * inline literals safely as long as the values themselves are stable.
 */
export default function usePhasedSequence(phases, { reduced = false } = {}) {
  const [phase, setPhase] = useState(reduced ? phases.length : 0);
  const key = phases.join(',');
  useEffect(() => {
    if (reduced) {
      setPhase(phases.length);
      return undefined;
    }
    setPhase(0);
    const timers = [];
    let elapsed = 0;
    phases.forEach((duration, idx) => {
      elapsed += duration;
      timers.push(setTimeout(() => setPhase(idx + 1), elapsed));
    });
    return () => timers.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduced, key]);
  return phase;
}
