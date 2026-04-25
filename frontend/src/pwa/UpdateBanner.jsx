import { RefreshCw } from 'lucide-react';
import { usePwaStatus } from './PwaStatusProvider';

/**
 * UpdateBanner — a thin top banner shown when a new service worker is
 * waiting. Mounted globally in App.jsx; sits at the top of the page
 * above the sticky header. Clicking Reload activates the waiting SW
 * (which auto-reloads the page).
 */
export default function UpdateBanner() {
  const { updateReady, applyUpdate } = usePwaStatus();
  if (!updateReady) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-3 bg-sheikah-teal-deep text-ink-page-rune-glow px-4 py-2 text-caption"
    >
      <RefreshCw size={14} aria-hidden="true" />
      <span>New version available.</span>
      {/* intentional: raw <button> with inline link styling — the Button primitive's variants don't fit this "underlined text link inside a colored bar" treatment */}
      <button
        type="button"
        onClick={applyUpdate}
        className="font-medium underline underline-offset-2 hover:opacity-80"
      >
        Reload
      </button>
    </div>
  );
}
