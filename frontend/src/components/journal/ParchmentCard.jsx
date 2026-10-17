import { forwardRef } from 'react';
import PedestalImage from '../../pedestal/PedestalImage';
import '../../pedestal/storybook-accents.css';

/**
 * Shared storybook panel. Legacy variant/decoration props remain compatible
 * with existing pages; every surface now has rounded edges and soft accents.
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
  const decorated = Boolean(flourish || seal);

  return (
    <Tag
      ref={ref}
      className={`${base} ${toneClasses} ${variantClasses} ${decorated ? 'storybook-panel' : ''} ${className}`}
      data-storybook-panel={decorated ? 'true' : undefined}
      {...props}
    >
      {decorated && <StorybookCorners flourish={flourish} seal={seal} />}
      {children}
    </Tag>
  );
});

function StorybookCorners({ flourish, seal }) {
  const positions = {
    'top-left': 'top-2 left-2',
    'top-right': 'top-2 right-2 storybook-corner--right',
    'bottom-left': 'bottom-2 left-2 storybook-corner--bottom',
    'bottom-right': 'bottom-2 right-2 storybook-corner--end',
  };
  // Combined legacy props request the same two accents, never extra ornaments.
  const corners = flourish ? ['top-left', 'bottom-right'] : [positions[seal] ? seal : 'top-right'];
  return <>
    {corners.map(position => <span key={position} className={`storybook-corner ${positions[position]}`} aria-hidden="true" data-storybook-corner>
      <PedestalImage assetId="corner-decor-01" fallback="" />
    </span>)}
  </>;
}

export default ParchmentCard;
