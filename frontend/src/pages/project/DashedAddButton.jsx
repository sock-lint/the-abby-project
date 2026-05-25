import { Plus } from 'lucide-react';

/**
 * DashedAddButton — the dashed-border "add X" affordance used inside the
 * project Plan tab. Lives here rather than in `components/` because only
 * PlanTab uses it today (per the page-specific card-placement rule in
 * frontend/CLAUDE.md). Promote when a second page picks it up.
 *
 * Sizes:
 *   - `md` (default) — for the outer "add milestone/step/resource" row
 *   - `sm` — for the nested "add step here" affordance inside a milestone
 */
const SIZE_CLASSES = {
  md: 'py-2.5 text-body min-w-[140px]',
  sm: 'py-1.5 text-caption',
};

const ICON_SIZE = { md: 16, sm: 12 };

export default function DashedAddButton({
  children,
  onClick,
  size = 'md',
  className = '',
}) {
  const sizeClass = SIZE_CLASSES[size] || SIZE_CLASSES.md;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 flex items-center justify-center gap-2 rounded-lg border-2 border-dashed border-ink-page-shadow font-script text-ink-secondary hover:text-ink-primary hover:border-sheikah-teal/60 transition-colors ${sizeClass} ${className}`}
    >
      <Plus size={ICON_SIZE[size] || 16} />
      {children}
    </button>
  );
}
