import ParchmentCard from './journal/ParchmentCard';

/**
 * EmptyState — a blank journal page with an ink flourish. Used whenever a
 * list or collection has no items yet.
 */
export default function EmptyState({ children, icon, action, className = '' }) {
  return (
    <ParchmentCard
      flourish
      role="status"
      className={`text-center py-10 text-ink-secondary font-body italic ${className}`}
    >
      {icon && <div className="flex justify-center mb-2 text-ink-whisper">{icon}</div>}
      {children}
      {action && <div className="mt-4 not-italic">{action}</div>}
    </ParchmentCard>
  );
}
