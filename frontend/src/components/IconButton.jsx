import { forwardRef } from 'react';
import {
  buttonPrimary,
  buttonSecondary,
  buttonDanger,
  buttonGhost,
  buttonSuccess,
} from '../constants/styles';

const VARIANT_CLASSES = {
  primary: buttonPrimary,
  secondary: buttonSecondary,
  danger: buttonDanger,
  ghost: buttonGhost,
  success: buttonSuccess,
};

const SIZE_CLASSES = {
  sm: 'p-1.5',
  md: 'p-2',
  lg: 'p-2.5',
};

/**
 * IconButton — square-footprint button for icon-only affordances. Requires
 * aria-label since there is no visible text. Missing aria-label triggers a
 * console.error in dev so the gap is visible during work.
 */
const IconButton = forwardRef(function IconButton(
  {
    variant = 'ghost',
    size = 'md',
    type = 'button',
    'aria-label': ariaLabel,
    className = '',
    children,
    ...rest
  },
  ref,
) {
  if (!import.meta.env.PROD && !ariaLabel) {
    console.error(
      'IconButton requires aria-label so screen-reader users can identify the action.',
    );
  }
  const variantClass = VARIANT_CLASSES[variant] || VARIANT_CLASSES.ghost;
  const sizeClass = SIZE_CLASSES[size] || SIZE_CLASSES.md;
  return (
    <button
      ref={ref}
      type={type}
      aria-label={ariaLabel}
      className={`${variantClass} ${sizeClass} inline-flex items-center justify-center rounded-lg ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
});

export default IconButton;
