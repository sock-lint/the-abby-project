/**
 * ParchmentSkeleton — content-aware skeleton placeholders that eliminate
 * layout shift while data loads. Matches the ParchmentCard/HeroPrimaryCard
 * shapes so the page structure is recognizable before content paints.
 *
 * Variants:
 *   - "card"  : a ParchmentCard-shaped skeleton (~120px)
 *   - "hero"  : a wider/taller skeleton for HeroPrimaryCard (~180px)
 *   - "rail"  : horizontal row of small card skeletons (~96px each)
 *   - "list"  : stacked line skeletons for quest-log-style entries
 *
 * The shimmer animation is self-contained via an injected <style> tag so
 * index.css stays untouched.
 */

const SHIMMER_STYLE_ID = 'parchment-shimmer-keyframes';

function ensureShimmerStyle() {
  if (typeof document === 'undefined') return;
  if (document.getElementById(SHIMMER_STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = SHIMMER_STYLE_ID;
  style.textContent = `
@keyframes parchment-shimmer {
  0% { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}
@media (prefers-reduced-motion: reduce) {
  .parchment-shimmer { animation: none !important; }
}
`;
  document.head.appendChild(style);
}

const shimmerClasses =
  'parchment-shimmer rounded-md';

const shimmerStyle = {
  backgroundImage:
    'linear-gradient(90deg, transparent 0%, var(--color-ink-page-rune-glow, #fff8e0) 40%, transparent 80%)',
  backgroundSize: '800px 100%',
  backgroundRepeat: 'no-repeat',
  animation: 'parchment-shimmer 1.6s ease-in-out infinite',
};

/** A single shimmer bar — the atomic building block. */
function ShimmerBar({ className = '', style: extraStyle }) {
  return (
    <div
      aria-hidden="true"
      className={`${shimmerClasses} bg-ink-page-shadow/30 ${className}`}
      style={{ ...shimmerStyle, ...extraStyle }}
    />
  );
}

/** Card variant — mirrors a ParchmentCard with inner content bars. */
function CardSkeleton() {
  return (
    <div className="rounded-xl border border-ink-page-shadow bg-ink-page-aged p-5 space-y-3 h-[120px]">
      <ShimmerBar className="h-4 w-3/5" />
      <ShimmerBar className="h-3 w-4/5" />
      <ShimmerBar className="h-3 w-2/5" />
    </div>
  );
}

/** Hero variant — taller, matches HeroPrimaryCard proportions. */
function HeroSkeleton() {
  return (
    <div className="rounded-xl border border-ink-page-shadow bg-ink-page-rune-glow p-5 space-y-4 h-[180px]">
      <div className="flex items-center gap-3">
        <ShimmerBar className="h-10 w-10 rounded-full shrink-0" />
        <div className="flex-1 space-y-2">
          <ShimmerBar className="h-5 w-2/3" />
          <ShimmerBar className="h-3 w-1/3" />
        </div>
      </div>
      <ShimmerBar className="h-4 w-4/5" />
      <ShimmerBar className="h-8 w-1/3 rounded-lg" />
    </div>
  );
}

/** Rail variant — horizontal row of small card skeletons. */
function RailSkeleton({ count = 4 }) {
  return (
    <div className="flex gap-3 overflow-hidden">
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          className="shrink-0 w-24 rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3 space-y-2"
        >
          <ShimmerBar className="h-8 w-8 rounded-full mx-auto" />
          <ShimmerBar className="h-3 w-full" />
        </div>
      ))}
    </div>
  );
}

/** List variant — stacked line skeletons for quest-log entries. */
function ListSkeleton({ count = 3 }) {
  const widths = ['w-4/5', 'w-3/5', 'w-2/3', 'w-5/6', 'w-1/2'];
  return (
    <div className="rounded-xl border border-ink-page-shadow bg-ink-page-aged p-5 space-y-4">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <ShimmerBar className="h-4 w-4 rounded-full shrink-0" />
          <ShimmerBar className={`h-4 ${widths[i % widths.length]}`} />
        </div>
      ))}
    </div>
  );
}

const VARIANT_MAP = {
  card: CardSkeleton,
  hero: HeroSkeleton,
  rail: RailSkeleton,
  list: ListSkeleton,
};

const DEFAULT_COUNT = {
  card: 1,
  hero: 1,
  rail: 4,
  list: 3,
};

export default function ParchmentSkeleton({
  variant = 'card',
  count,
  className = '',
}) {
  ensureShimmerStyle();

  const Renderer = VARIANT_MAP[variant] || CardSkeleton;
  const resolvedCount = count ?? DEFAULT_COUNT[variant] ?? 1;

  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading"
      className={className}
    >
      <Renderer count={resolvedCount} />
    </div>
  );
}
