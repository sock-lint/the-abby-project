import { forwardRef } from 'react';
import { formHelpClass, formErrorClass } from '../../constants/styles';
import useFieldIds from './useFieldIds';

/**
 * ToggleField — labeled on/off switch with proper ``aria-pressed`` /
 * ``aria-describedby`` semantics and keyboard support (the underlying
 * ``<button>`` handles Space/Enter toggling natively).
 *
 * Closes the gap where pages were hand-rolling toggle buttons with
 * ad-hoc Tailwind ``translate-x-5`` track styling and forgetting at
 * least one accessibility attribute. Use this anywhere a setting flips
 * a boolean.
 *
 * Props:
 *   ``checked``: boolean — current state.
 *   ``onChange(next: boolean)``: receiver. Called with the new state,
 *     not an event, so the API matches a controlled checkbox without
 *     callers having to read ``e.target.checked``.
 *   ``label``: string — visible text. ``labelNode`` for richer markup.
 *   ``disabled``: optional. ``aria-disabled`` is set automatically.
 *   ``error`` / ``helpText``: same as TextField.
 */
const ToggleField = forwardRef(function ToggleField(
  {
    checked,
    onChange,
    label,
    labelNode,
    error,
    helpText,
    id: idProp,
    className = '',
    disabled = false,
    ...rest
  },
  ref,
) {
  const { id, helpId, errorId, describedBy } = useFieldIds({ idProp, helpText, error });

  const handleToggle = () => {
    if (disabled) return;
    onChange?.(!checked);
  };

  const trackClass = checked
    ? 'bg-sheikah-teal-deep border-sheikah-teal-deep'
    : 'bg-ink-page-aged border-ink-page-shadow';
  const knobOffset = checked ? 'translate-x-5' : 'translate-x-0';

  return (
    <div className={className}>
      <div className="flex items-center gap-3">
        <button
          ref={ref}
          id={id}
          type="button"
          role="switch"
          aria-checked={checked}
          aria-pressed={checked}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={describedBy}
          aria-disabled={disabled || undefined}
          onClick={handleToggle}
          disabled={disabled}
          className={
            'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full ' +
            'border transition-colors focus:outline-none focus:ring-2 ' +
            `focus:ring-sheikah-teal/40 ${trackClass} ` +
            (disabled ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer')
          }
          {...rest}
        >
          <span
            aria-hidden="true"
            className={
              'inline-block h-5 w-5 rounded-full bg-ink-page-rune-glow ' +
              `shadow-sm transition-transform ${knobOffset}`
            }
          />
        </button>
        {(labelNode ?? label) && (
          <label htmlFor={id} className="text-body text-ink-primary cursor-pointer">
            {labelNode ?? label}
          </label>
        )}
      </div>
      {helpText && !error && <p id={helpId} className={formHelpClass}>{helpText}</p>}
      {error && <p id={errorId} role="alert" className={formErrorClass}>{error}</p>}
    </div>
  );
});

export default ToggleField;
