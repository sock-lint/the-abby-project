import { useEffect, useState } from 'react';

/**
 * Loader — inked compass rose spinner. Matches the Hyrule Field Notes
 * aesthetic with a slowly rotating Sheikah ring.
 *
 * Delayed-show behavior: the spinner only appears after `delayMs` (default
 * 200ms). Fast responses that resolve before the delay never show the
 * spinner, which prevents the flash that used to read as "retry" during
 * page transitions.
 */
export default function Loader({ delayMs = 200 }) {
  const [visible, setVisible] = useState(delayMs <= 0);

  useEffect(() => {
    if (delayMs <= 0) return undefined;
    const t = setTimeout(() => setVisible(true), delayMs);
    return () => clearTimeout(t);
  }, [delayMs]);

  if (!visible) return null;

  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading"
      className="flex items-center justify-center py-12"
    >
      <div className="relative w-10 h-10">
        <div
          className="absolute inset-0 border-2 border-sheikah-teal-deep border-t-transparent border-l-transparent rounded-full animate-spin"
          style={{ animationDuration: '1.1s' }}
        />
        <div
          className="absolute inset-1.5 border border-ink-page-shadow border-dashed rounded-full"
          style={{ animation: 'spin 3.8s linear infinite reverse' }}
        />
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="w-1.5 h-1.5 rounded-full bg-sheikah-teal-deep" />
        </div>
      </div>
    </div>
  );
}
