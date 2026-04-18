import { OP_GLYPH } from './activity.constants';

/**
 * Renders the calculation breakdown for one ActivityEvent.
 *
 * Input: the ``context.breakdown`` array — each step is
 *   { label: string, value: string|number, op: '+' | '-' | '×' | '÷' | '=' | 'note' }
 *
 * The final operator-bearing row uses ``op === '='`` to indicate the result;
 * ``note`` rows render without an operator (for informational lines like
 * "item: Blue Potion (rare)").
 */
export default function BreakdownStrip({ breakdown }) {
  if (!Array.isArray(breakdown) || breakdown.length === 0) return null;
  return (
    <ul className="mt-2 space-y-1 text-caption text-ink-secondary font-body">
      {breakdown.map((step, i) => {
        const glyph = OP_GLYPH[step.op];
        return (
          <li key={i} className="flex items-baseline gap-2">
            {glyph && (
              <span
                aria-hidden="true"
                className="w-4 text-right text-ink-whisper"
              >
                {glyph}
              </span>
            )}
            {!glyph && <span aria-hidden="true" className="w-4" />}
            <span className="text-ink-primary">{step.label}</span>
            <span className="text-ink-whisper">·</span>
            <span className="font-mono">{String(step.value)}</span>
          </li>
        );
      })}
    </ul>
  );
}
