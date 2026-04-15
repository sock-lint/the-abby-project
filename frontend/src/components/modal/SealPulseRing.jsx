// One-shot teal ring that radiates outward from the modal card on mount,
// reinforcing the "stamp" metaphor. Pure CSS keyframe (animate-seal-pulse),
// auto-disabled under prefers-reduced-motion.
//
// Render as a sibling of the card (positioned absolutely over it), inheriting
// the card's border radius via the `rounded` prop.
export default function SealPulseRing({ rounded = 'rounded-2xl', className = '' }) {
  return (
    <span
      aria-hidden="true"
      className={`pointer-events-none absolute inset-0 ${rounded} animate-seal-pulse ${className}`}
      style={{
        boxShadow:
          '0 0 0 2px rgba(77, 208, 225, 0.55), 0 0 22px rgba(77, 208, 225, 0.45)',
      }}
    />
  );
}
