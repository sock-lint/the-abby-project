import ApprovalButtons from './ApprovalButtons';

/**
 * Generic parent-approval queue section.
 *
 * Renders a heading followed by a list of items. For each item, the caller
 * provides a render function via `children` that receives `{ item, actions }`
 * — `actions` is the pre-wired `<ApprovalButtons>` node that calls
 * `onApprove(item.id)` / `onReject(item.id)`. The caller is responsible for
 * wrapping the row in its own `<ParchmentCard>` so each queue (chore row,
 * homework card with proof gallery, redemption row, exchange row) stays free
 * to choose its layout.
 *
 * Returns null when `items` is empty (queues stay out of sight unless
 * something is actually pending), unless `emptyText` is given.
 */
export default function ApprovalQueue({
  items, title, icon, emptyText, onApprove, onReject, children,
}) {
  const header = (title || icon) && (
    <h2 className="font-display text-lg font-bold mb-3 flex items-center gap-2">
      {icon}{title}
    </h2>
  );

  if (!items?.length) {
    if (!emptyText) return null;
    return (
      <div>
        {header}
        <p className="text-sm text-ink-whisper">{emptyText}</p>
      </div>
    );
  }

  return (
    <div>
      {header}
      <div className="space-y-2">
        {items.map((item) => {
          const actions = (
            <ApprovalButtons
              onApprove={() => onApprove(item.id)}
              onReject={() => onReject(item.id)}
            />
          );
          return children({ item, actions });
        })}
      </div>
    </div>
  );
}
