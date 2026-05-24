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
  { variant = 'primary', size = 'md', type = 'button', loading = false, className = '', children, ...rest },
  ref,
) {
  const variantClass = VARIANT_CLASSES[variant] || VARIANT_CLASSES.primary;
  const sizeClass = SIZE_CLASSES[size] || SIZE_CLASSES.md;
  return (
    <button
      ref={ref}
      type={type}
      disabled={loading || rest.disabled}
      className={`${variantClass} ${sizeClass} ${className}`}
      {...rest}
    >
      {loading ? (
        <span className="inline-flex items-center gap-1.5">
          <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="2" opacity="0.3" />
            <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <span>{typeof children === 'string' ? 'Saving…' : children}</span>
        </span>
      ) : (
        children
      )}
    </button>
  );
});

export default Button;
