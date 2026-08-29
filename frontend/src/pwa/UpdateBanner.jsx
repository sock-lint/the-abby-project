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
    // This is the first in-flow element on the page, and index.html ships
    // viewport-fit=cover, so in the installed PWA the banner drew straight
    // under the iOS status bar: a ~36px strip swallowed whole by a ~59px
    // inset on Dynamic Island iPhones, with the Reload button sitting in the
    // zone where taps go to the OS instead of the page. Padding the inset
    // (with the teal extending beneath it, so the strip still reads as one
    // band) mirrors JournalShell's sticky header. The left/right insets
    // matter in landscape, where the sensor housing eats ~47px.
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-3 bg-sheikah-teal-deep text-ink-page-rune-glow
                 pt-[calc(env(safe-area-inset-top)+0.5rem)] pb-2
                 pl-[max(1rem,env(safe-area-inset-left))]
                 pr-[max(1rem,env(safe-area-inset-right))] text-caption"
    >
      <RefreshCw size={14} aria-hidden="true" />
      <span>New version available.</span>
      {/* intentional: raw <button> with inline link styling — the Button primitive's variants don't fit this "underlined text link inside a colored bar" treatment. The padding + negative margin keeps the 44px hit area without growing the band. */}
      <button
        type="button"
        onClick={applyUpdate}
        className="min-h-11 -my-2 px-2 flex items-center font-medium underline underline-offset-2 hover:opacity-80"
      >
        Reload
      </button>
    </div>
  );
}
