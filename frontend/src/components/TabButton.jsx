// Bookmark-ribbon tab button used across filter bars and sub-tabs.
// Reskinned for the Hyrule Field Notes aesthetic — parchment panels with
// a Sheikah-teal accent ribbon when active.
export default function TabButton({ active, onClick, children, className = '' }) {
  const base =
    'px-3 py-2 min-h-[44px] flex items-center rounded-lg font-display text-sm border transition-colors';
  const activeCls =
    'border-sheikah-teal-deep bg-sheikah-teal/15 text-ink-primary';
  const idleCls =
    'border-ink-page-shadow bg-ink-page-aged text-ink-secondary hover:text-ink-primary hover:border-sheikah-teal/50';
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
