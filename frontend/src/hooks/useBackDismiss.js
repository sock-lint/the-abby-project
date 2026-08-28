import { useEffect, useId, useRef } from 'react';

/**
 * Android back (and the iOS edge-swipe) is the universal "dismiss this
 * overlay" gesture in an installed PWA with no browser chrome. Without a
 * sentinel the press navigates away from the page entirely, throwing away
 * whatever state sat underneath (the Sketchbook's filter and scroll
 * position, a homework submission the proof photo belongs to).
 *
 * Same trick BottomSheet uses (components/BottomSheet.jsx): push one history
 * entry when the overlay opens, close the overlay when it pops, and consume
 * that entry again on unmount if it is still ours.
 *
 * Use it from a component that only mounts while the overlay is open, or
 * pass `active` when the overlay is rendered conditionally inside a
 * longer-lived component.
 *
 * @param {() => void} onDismiss — called when the back gesture pops our entry
 * @param {boolean} [active]     — false leaves history untouched
 */
export default function useBackDismiss(onDismiss, active = true) {
  const sentinelId = useId();
  const dismissRef = useRef(onDismiss);
  useEffect(() => { dismissRef.current = onDismiss; }, [onDismiss]);
  useEffect(() => {
    if (!active) return undefined;
    window.history.pushState({ abbyOverlay: sentinelId }, '');
    const handlePop = () => { dismissRef.current?.(); };
    window.addEventListener('popstate', handlePop);
    return () => {
      window.removeEventListener('popstate', handlePop);
      // Only when the sentinel is still the current entry — if the overlay
      // closed *because* of a back press it has already been consumed, and
      // popping again would navigate the page underneath.
      if (window.history.state?.abbyOverlay === sentinelId) window.history.back();
    };
  }, [sentinelId, active]);
}
