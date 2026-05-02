import { forwardRef } from 'react';
import {
  inputClass,
  formLabelClass,
  formHelpClass,
  formErrorClass,
} from '../../constants/styles';
import useFieldIds from './useFieldIds';

// "filter" variant: compact toolbar select with no fixed full-width sizing,
// smaller padding, and the ``text-caption`` token. Closes the previous
// gap where pages (e.g. ``pages/Projects.jsx`` filter selects) had to drop
// down to raw ``<select className={inputClass} ...>`` markup with manual
// dimensional overrides.
const FILTER_VARIANT_CLASS =
  'rounded-md border border-ink-page-shadow bg-ink-page-aged ' +
  'px-2 py-1.5 text-caption text-ink-primary w-auto ' +
  'focus:outline-none focus:ring-2 focus:ring-sheikah-teal/40';

/**
 * SelectField — labeled <select> with built-in error and helpText slots.
 * Mirrors the TextField API; consumers pass <option> children directly.
 *
 * Pass ``variant="filter"`` for a compact toolbar select (no full-width
 * sizing, smaller padding) — used by listing-page filter dropdowns that
 * previously dropped to raw markup.
 */
const SelectField = forwardRef(function SelectField(
  {
    label, error, helpText,
    id: idProp, className = '',
    variant = 'default',
    children, ...rest
  },
  ref,
) {
  const { id, helpId, errorId, describedBy } = useFieldIds({ idProp, helpText, error });
  const selectClass = variant === 'filter' ? FILTER_VARIANT_CLASS : inputClass;

  return (
    <div className={className}>
      {label && <label htmlFor={id} className={formLabelClass}>{label}</label>}
      <select
        ref={ref}
        id={id}
        className={selectClass}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        {...rest}
      >
        {children}
      </select>
      {helpText && !error && <p id={helpId} className={formHelpClass}>{helpText}</p>}
      {error && <p id={errorId} role="alert" className={formErrorClass}>{error}</p>}
    </div>
  );
});

export default SelectField;
