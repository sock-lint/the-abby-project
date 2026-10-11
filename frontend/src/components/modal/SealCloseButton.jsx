import { X } from 'lucide-react';

// Preserve the shared close control's API, focus and 44px touch target.
// Both legacy variants now belong to the same soft storybook surface.
export default function SealCloseButton({
  onClick, disabled = false, ariaLabel = 'Close', variant = 'ember',
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className={`relative min-h-11 min-w-11 h-11 w-11 flex items-center justify-center rounded-full border border-ink-page-shadow bg-ink-page transition-colors hover:bg-ink-page-shadow/50 disabled:opacity-50 disabled:pointer-events-none ${variant === 'teal' ? 'text-sheikah-teal' : 'text-ink-secondary'}`}
    >
      <X size={18} strokeWidth={2.5} aria-hidden="true" />
    </button>
  );
}
