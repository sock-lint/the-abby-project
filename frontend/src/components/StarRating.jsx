import PedestalImage from '../pedestal/PedestalImage';
import '../pedestal/storybook-accents.css';

/** Existing difficulty scale, with proportional artwork and readable fallback. */
export default function StarRating({ value = 0, max = 5, title = null, className = '' }) {
  const filled = Math.max(0, Math.min(max, value));
  return (
    <span title={title} role="img" aria-label={title || `Difficulty: ${filled} out of ${max}`} className={`inline-flex flex-wrap items-center gap-0.5 ${className}`}>
      {Array.from({ length: max }, (_, index) => <PedestalImage
        key={index}
        assetId={index < filled ? 'star-lit' : 'star-unlit'}
        fallback={index < filled ? '★' : '☆'}
        className={`storybook-star ${index < filled ? 'text-gold-leaf' : 'text-ink-whisper/60'}`}
      />)}
    </span>
  );
}
