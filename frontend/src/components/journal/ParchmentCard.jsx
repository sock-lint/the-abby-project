import { forwardRef } from 'react';
import { Flower2, Sparkles } from 'lucide-react';
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

  return (
    <Tag
      ref={ref}
      className={`${base} ${toneClasses} ${variantClasses} ${flourish === 'storybook' ? 'storybook-panel' : ''} ${className}`}
      {...props}
    >
      {flourish === 'storybook' ? <StorybookCorners /> : flourish && <CornerFlourishes />}
      {seal && <WaxSeal position={seal === true ? 'top-right' : seal} />}
      {flourish === 'storybook'
        ? <div className="storybook-panel__content" data-storybook-content>{children}</div>
        : children}
    </Tag>
  );
});

function StorybookCorners() {
  return <>
    {['', 'storybook-corner--end'].map((position) => (
      <span key={position} className={`storybook-corner ${position}`} aria-hidden="true" data-storybook-corner>
        <PedestalImage assetId="corner-decor-01" fallback="" />
      </span>
    ))}
  </>;
}

function CornerFlourishes() {
  return (
    <>
      {['top-2 left-2', 'top-2 right-2', 'bottom-2 left-2', 'bottom-2 right-2'].map((position) => (
        <Sparkles key={position} aria-hidden="true" className={`absolute ${position} w-4 h-4 text-sheikah-teal opacity-20 pointer-events-none`} />
      ))}
    </>
  );
}

function WaxSeal({ position = 'top-right' }) {
  const positions = {
    'top-right': 'top-2 right-2', 'top-left': 'top-2 left-2',
    'bottom-right': 'bottom-2 right-2', 'bottom-left': 'bottom-2 left-2',
  };
  return (
    <Flower2
      aria-hidden="true"
      className={`absolute ${positions[position] || positions['top-right']} w-9 h-9 p-2 rounded-full bg-moss/10 text-moss pointer-events-none`}
    />
  );
}

export default ParchmentCard;
