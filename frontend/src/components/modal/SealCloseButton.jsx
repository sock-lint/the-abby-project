import { X } from 'lucide-react';

// Wax-seal close button. Replaces the bare <X> used across the modal family.
// Pure CSS: radial gradient (ember → ember-deep) with an inset highlight so
// the surface reads like pressed wax. The X sits embossed in the center.
//
// Variants:
//   "ember" (default) — warm red seal, fits FormModal / BottomSheet
//   "teal"             — sheikah teal seal, optional for neutral surfaces
export default function SealCloseButton({
  onClick,
  disabled = false,
  ariaLabel = 'Close',
  variant = 'ember',
}) {
  const gradient =
    variant === 'teal'
      ? 'radial-gradient(circle at 30% 30%, #4dd0e1 0%, #26a69a 55%, #1b7970 100%)'
      : 'radial-gradient(circle at 30% 30%, #e88a5e 0%, #d97548 55%, #a04a28 100%)';

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className="relative min-h-10 min-w-10 h-10 w-10 flex items-center justify-center rounded-full transition-transform duration-200 hover:scale-105 active:scale-95 disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none"
      style={{
        background: gradient,
        boxShadow:
          'inset 0 1px 2px rgba(255, 248, 224, 0.45), inset 0 -2px 4px rgba(45, 31, 21, 0.45), 0 2px 4px rgba(45, 31, 21, 0.35)',
      }}
    >
      <X
        size={16}
        strokeWidth={2.5}
        className="text-ink-page-rune-glow"
        style={{ filter: 'drop-shadow(0 1px 1px rgba(45, 31, 21, 0.55))' }}
      />
    </button>
  );
}
