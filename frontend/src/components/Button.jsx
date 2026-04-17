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
  sm: 'px-3 py-1 text-sm',
  md: 'px-4 py-2',
  lg: 'px-5 py-3 text-lg',
};

/**
 * Button — single source of truth for tappable parchment buttons.
 * Wraps the class strings from constants/styles.js so call sites read
 * the variant as a prop instead of remembering to import the right name.
 *
 * For icon-only buttons (no visible text), use <IconButton> instead — it
 * enforces an aria-label.
 */
const Button = forwardRef(function Button(
  { variant = 'primary', size = 'md', type = 'button', className = '', children, ...rest },
  ref,
) {
  const variantClass = VARIANT_CLASSES[variant] || VARIANT_CLASSES.primary;
  const sizeClass = SIZE_CLASSES[size] || SIZE_CLASSES.md;
  return (
    <button
      ref={ref}
      type={type}
      className={`${variantClass} ${sizeClass} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
});

export default Button;
