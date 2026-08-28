import { forwardRef } from 'react';
import {
  inputClass,
  formLabelClass,
  formHelpClass,
  formErrorClass,
} from '../../constants/styles';
import useFieldIds from './useFieldIds';

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
  const { id, helpId, errorId, describedBy } = useFieldIds({ idProp, helpText, error });

  // Mobile keypads: number inputs raise the large numeric/decimal keypad
  // instead of the cramped full keyboard. Derived only when the call site
  // doesn't pass its own inputMode — signed-amount fields (the coin/payment
  // adjust modals, forge budget adjustments) pass inputMode="text" because
  // the iOS numeric and decimal pads have no minus key.
  const derivedInputMode =
    rest.type === 'number'
      ? (String(rest.step ?? '').includes('.') ? 'decimal' : 'numeric')
      : undefined;

  return (
    <div className={className}>
      {label && <label htmlFor={id} className={formLabelClass}>{label}</label>}
      <input
        ref={ref}
        id={id}
        className={inputClass}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        inputMode={derivedInputMode}
        {...rest}
      />
      {helpText && !error && <p id={helpId} className={formHelpClass}>{helpText}</p>}
      {error && <p id={errorId} role="alert" className={formErrorClass}>{error}</p>}
    </div>
  );
});

export default TextField;
