import { forwardRef } from 'react';
import {
  inputClass,
  formLabelClass,
  formHelpClass,
  formErrorClass,
} from '../../constants/styles';
import useFieldIds from './useFieldIds';

/**
 * SelectField — labeled <select> with built-in error and helpText slots.
 * Mirrors the TextField API; consumers pass <option> children directly.
 */
const SelectField = forwardRef(function SelectField(
  { label, error, helpText, id: idProp, className = '', children, ...rest },
  ref,
) {
  const { id, helpId, errorId, describedBy } = useFieldIds({ idProp, helpText, error });

  return (
    <div className={className}>
      {label && <label htmlFor={id} className={formLabelClass}>{label}</label>}
      <select
        ref={ref}
        id={id}
        className={inputClass}
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
