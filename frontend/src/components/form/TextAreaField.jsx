import { forwardRef } from 'react';
import {
  inputClass,
  formLabelClass,
  formHelpClass,
  formErrorClass,
} from '../../constants/styles';
import useFieldIds from './useFieldIds';

/**
 * TextAreaField — labeled <textarea> with built-in error and helpText slots.
 * Mirrors the TextField/SelectField API. `rows` defaults to 3.
 */
const TextAreaField = forwardRef(function TextAreaField(
  { label, error, helpText, id: idProp, className = '', rows = 3, ...rest },
  ref,
) {
  const { id, helpId, errorId, describedBy } = useFieldIds({ idProp, helpText, error });

  return (
    <div className={className}>
      {label && <label htmlFor={id} className={formLabelClass}>{label}</label>}
      <textarea
        ref={ref}
        id={id}
        rows={rows}
        className={inputClass}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
        {...rest}
      />
      {helpText && !error && <p id={helpId} className={formHelpClass}>{helpText}</p>}
      {error && <p id={errorId} role="alert" className={formErrorClass}>{error}</p>}
    </div>
  );
});

export default TextAreaField;
