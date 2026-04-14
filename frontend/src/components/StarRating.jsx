export default function StarRating({ value = 0, max = 5, title = null }) {
  const filled = Math.max(0, Math.min(max, value));
  return (
    <span title={title}>{'★'.repeat(filled)}{'☆'.repeat(max - filled)}</span>
  );
}
