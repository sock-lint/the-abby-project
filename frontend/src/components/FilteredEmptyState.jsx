import Button from './Button';
import EmptyState from './EmptyState';

/**
 * FilteredEmptyState — distinct empty state for when a CatalogSearch filter
 * yields zero results. Clearly communicates "your filter hides everything"
 * (vs. "no items exist") and provides a one-tap clear action.
 */
export default function FilteredEmptyState({ query, onClear, icon }) {
  return (
    <EmptyState
      icon={icon}
      action={
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear filter
        </Button>
      }
    >
      No matches for &ldquo;{query}&rdquo;
    </EmptyState>
  );
}
