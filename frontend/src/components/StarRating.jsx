/**
 * StarRating — dragon-sigil rating used for project/homework difficulty.
 * Filled glyphs render in gold-leaf, empty in ink-whisper.
 */
export default function StarRating({ value = 0, max = 5, title = null, className = '' }) {
  const filled = Math.max(0, Math.min(max, value));
  return (
    <span title={title} className={`inline-flex items-center tracking-wide ${className}`}>
      <span className="text-gold-leaf">{'★'.repeat(filled)}</span>
      <span className="text-ink-whisper/60">{'☆'.repeat(max - filled)}</span>
    </span>
  );
}
