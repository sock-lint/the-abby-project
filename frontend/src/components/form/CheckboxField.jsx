import { forwardRef } from 'react';
import { formHelpClass, formErrorClass } from '../../constants/styles';
import useFieldIds from './useFieldIds';

/**
 * CheckboxField — labeled checkbox with the same useId / aria-invalid /
 * aria-describedby plumbing as TextField / SelectField. Closes the gap
 * where pages were rendering raw ``<input type="checkbox">`` wrapped in
 * a ``<label>`` and re-implementing the spacing each time.
 *
 * Pass the label as a prop (string) — for richer label markup, render
 * ``<CheckboxField labelNode={<>my <em>label</em></>}>``.
 *
 * The ``className`` prop styles the outer wrapper (so callers can add
 * margins). The control itself uses Tailwind defaults for now.
 */
const CheckboxField = forwardRef(function CheckboxField(
  {
    label,
    labelNode,
    error,
    helpText,
    id: idProp,
    className = '',
    inputClassName = '',
    ...rest
  },
  ref,
) {
  const { id, helpId, errorId, describedBy } = useFieldIds({ idProp, helpText, error });

  return (
    <div className={className}>
      <label
        htmlFor={id}
        className="flex items-center gap-2 cursor-pointer select-none"
      >
        <input
          ref={ref}
          id={id}
          type="checkbox"
          className={`accent-sheikah-teal-deep ${inputClassName}`.trim()}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={describedBy}
          {...rest}
        />
        <span className="text-body text-ink-primary">
          {labelNode ?? label}
        </span>
      </label>
      {helpText && !error && <p id={helpId} className={formHelpClass}>{helpText}</p>}
      {error && <p id={errorId} role="alert" className={formErrorClass}>{error}</p>}
    </div>
  );
});

export default CheckboxField;
