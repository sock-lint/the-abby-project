/**
 * Sparkline — dependency-free SVG trend line for small stat strips.
 *
 * Props:
 *   data        : array of numbers, oldest first (required)
 *   label       : accessible description (required — role="img")
 *   strokeClass : Tailwind stroke-* class (default 'stroke-moss')
 *   height      : CSS height class (default 'h-7')
 *
 * All-zero data still paints a flat baseline so "nothing earned yet"
 * reads as a quiet line rather than a missing element. Renders null
 * only when there's no data at all.
 */
const VIEW_W = 120;
const VIEW_H = 28;
const PAD = 2;

export default function Sparkline({
  data = [], label, strokeClass = 'stroke-moss', height = 'h-7',
}) {
  if (!data.length) return null;

  const max = Math.max(...data, 1);
  const stepX = data.length > 1 ? VIEW_W / (data.length - 1) : VIEW_W;
  const points = data
    .map((v, i) => {
      const x = i * stepX;
      const y = PAD + (VIEW_H - 2 * PAD) * (1 - v / max);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
      className={`w-full ${height}`}
    >
      <polyline
        points={points}
        fill="none"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        className={strokeClass}
      />
    </svg>
  );
}
