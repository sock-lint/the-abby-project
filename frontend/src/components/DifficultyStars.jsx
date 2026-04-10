export default function DifficultyStars({ difficulty, max = 5 }) {
  return <span>{'★'.repeat(difficulty)}{'☆'.repeat(max - difficulty)}</span>;
}
