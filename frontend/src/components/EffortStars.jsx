export default function EffortStars({ level, max = 5 }) {
  return <span title={`Effort: ${level}/${max}`}>{'★'.repeat(level)}{'☆'.repeat(max - level)}</span>;
}
