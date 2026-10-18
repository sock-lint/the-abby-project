import { forwardRef } from 'react';

/**
 * Shared Meadow panel. Legacy decoration props remain accepted, but artwork
 * belongs in dedicated content areas rather than the panel's corners.
 */
const ParchmentCard = forwardRef(function ParchmentCard(
  {
    as: Tag = 'div',
    variant = 'plain',
    tone = 'default',
    flourish = false,
    seal = false,
    className = '',
    children,
    ...props
  },
  ref,
) {
  const toneClasses = {
    default: 'bg-ink-page-aged text-ink-primary',
    bright: 'bg-ink-page-rune-glow text-ink-primary',
    deep: 'bg-ink-page-shadow/80 text-ink-primary',
  }[tone];

  const variantClasses = {
    plain: 'border border-ink-page-shadow rounded-xl',
    deckle: 'deckle-edge border border-ink-page-shadow rounded-xl',
    sealed: 'border border-ink-page-shadow rounded-xl',
  }[variant];

  const base =
    'relative p-5 shadow-[0_8px_24px_-12px_var(--color-modal-shadow-strong)]';
  const contentLayout = flourish || seal ? 'min-w-0 [overflow-wrap:anywhere]' : '';

  return (
    <Tag
      ref={ref}
      className={`${base} ${toneClasses} ${variantClasses} ${contentLayout} ${className}`}
      {...props}
    >
      {children}
    </Tag>
  );
});

export default ParchmentCard;
