import ParchmentCard from './journal/ParchmentCard';

/**
 * EmptyState — a blank journal page with an ink flourish. Used whenever a
 * list or collection has no items yet.
 */
export default function EmptyState({ children, icon, className = '' }) {
  return (
    <ParchmentCard flourish className={`text-center py-10 text-ink-secondary font-body italic ${className}`}>
      {icon && <div className="flex justify-center mb-2 text-ink-whisper">{icon}</div>}
      {children}
    </ParchmentCard>
  );
}
