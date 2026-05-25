import { forwardRef } from 'react';
import {
  inputClass,
  formLabelClass,
  formHelpClass,
  formErrorClass,
} from '../../constants/styles';
import useFieldIds from './useFieldIds';

// "filter" variant: compact toolbar date input that matches SelectField's
// filter variant so a filter row mixing dropdowns + date inputs reads as
// one rhythm rather than two grafted-on visuals. See SelectField.jsx.
const FILTER_VARIANT_CLASS =
  'rounded-md border border-ink-page-shadow bg-ink-page-aged ' +
  'px-2 py-1.5 text-caption text-ink-primary w-auto ' +
  'focus:outline-none focus:ring-2 focus:ring-sheikah-teal/40';

/**
 * DateField — labeled <input type="date"> with the same useId / aria-invalid /
 * aria-describedby plumbing as TextField / SelectField. Closes the gap where
 * pages were hand-rolling raw date inputs with bespoke compact classes that
 * didn't match the form-primitive theming.
 *
 * Pass ``variant="filter"`` for a compact toolbar date input that matches
 * SelectField's filter variant — used in listing-page filter rows.
 */
const DateField = forwardRef(function DateField(
  {
    label, error, helpText,
    id: idProp, className = '',
    variant = 'default',
    ...rest
  },
  ref,
) {
  const { id, helpId, errorId, describedBy } = useFieldIds({ idProp, helpText, error });
  const fieldClass = variant === 'filter' ? FILTER_VARIANT_CLASS : inputClass;

  return (
    <div className={className}>
      {label && <label htmlFor={id} className={formLabelClass}>{label}</label>}
      <input
        ref={ref}
        id={id}
        type="date"
        className={fieldClass}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        {...rest}
      />
      {helpText && !error && <p id={helpId} className={formHelpClass}>{helpText}</p>}
      {error && <p id={errorId} role="alert" className={formErrorClass}>{error}</p>}
    </div>
  );
});

export default DateField;
