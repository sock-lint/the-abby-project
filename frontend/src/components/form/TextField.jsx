import { forwardRef, useId } from 'react';
import { inputClass } from '../../constants/styles';

const labelClass = 'font-script text-sm text-ink-secondary mb-1 block';
const helpClass = 'text-xs text-ink-whisper mt-1';
const errorClass = 'text-xs text-ember-deep mt-1';

/**
 * TextField — labeled input with built-in error and helpText slots,
 * proper htmlFor/id association via useId, and aria-invalid /
 * aria-describedby wiring. Forwards all native input props through ...rest.
 *
 * Replaces the hand-rolled `<label className="font-script ..."><input className={inputClass} />`
 * pattern used across the *FormModal cohort.
 */
const TextField = forwardRef(function TextField(
  { label, error, helpText, id: idProp, className = '', ...rest },
  ref,
) {
  const generatedId = useId();
  const id = idProp || generatedId;
  const helpId = helpText ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [helpId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={className}>
      {label && <label htmlFor={id} className={labelClass}>{label}</label>}
      <input
        ref={ref}
        id={id}
        className={inputClass}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        {...rest}
      />
      {helpText && !error && <p id={helpId} className={helpClass}>{helpText}</p>}
      {error && <p id={errorId} role="alert" className={errorClass}>{error}</p>}
    </div>
  );
});

export default TextField;
