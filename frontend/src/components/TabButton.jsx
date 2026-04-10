// Pill-style tab button used in filter bars across pages.
// The styling was duplicated in Achievements.jsx and ProjectIngest.jsx.
export default function TabButton({ active, onClick, children, className = '' }) {
  const base = 'px-3 py-1.5 rounded-lg text-xs font-medium border transition';
  const activeCls = 'border-amber-primary bg-amber-primary/10 text-amber-highlight';
  const idleCls = 'border-forge-border bg-forge-card text-forge-text-dim hover:text-forge-text';
  return (
    <button
      type="button"
      onClick={onClick}
      className={`${base} ${active ? activeCls : idleCls} ${className}`}
    >
      {children}
    </button>
  );
}
