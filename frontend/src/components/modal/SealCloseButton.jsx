import { X } from 'lucide-react';

// Wax-seal close button. Replaces the bare <X> used across the modal family.
// Pure CSS: radial gradient using a theme-invariant ember-tone palette
// (NOT --color-ember, which varies per cover). Inset highlight reads like
// pressed wax. The X sits embossed in the center.
//
// Variants:
//   "ember" (default) — warm red seal, fits BottomSheet / ConfirmDialog
//   "teal"             — sheikah teal seal, optional for neutral surfaces
export default function SealCloseButton({
  onClick,
  disabled = false,
  ariaLabel = 'Close',
  variant = 'ember',
}) {
  const gradient =
    variant === 'teal'
      ? 'radial-gradient(circle at 30% 30%, #4dd0e1 0%, #26a69a 55%, #1b7970 100%)' // intentional: theme-invariant teal seal palette — must NOT bind to --color-sheikah-* (varies per cover)
      : 'radial-gradient(circle at 30% 30%, #e88a5e 0%, #d97548 55%, #a04a28 100%)'; // intentional: theme-invariant ember seal palette — must NOT bind to --color-ember (varies per cover; e.g. Vigil inverts it light)

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={ariaLabel}
      className="relative min-h-11 min-w-11 h-11 w-11 flex items-center justify-center rounded-full transition-transform duration-200 hover:scale-105 active:scale-95 disabled:opacity-50 disabled:pointer-events-none focus-visible:outline-none"
      style={{
        background: gradient,
        // ink-tone shadow stops use --color-modal-* so per-cover overrides flow through;
        // the 0.45 highlight is intentionally one tick brighter than --color-modal-highlight (0.4)
        // because seal buttons live on a colored gradient, not parchment.
        boxShadow:
          'inset 0 1px 2px rgba(255, 248, 224, 0.45), inset 0 -2px 4px var(--color-modal-shadow), 0 2px 4px rgba(45, 31, 21, 0.35)',
      }}
    >
      <X
        size={16}
        strokeWidth={2.5}
        className="text-ink-page-rune-glow"
        style={{ filter: 'drop-shadow(0 1px 1px var(--color-modal-shadow-strong))' }}
      />
    </button>
  );
}
