import { forwardRef } from 'react';

/**
 * ParchmentCard — the foundation panel of the Hyrule Field Notes system.
 *
 * Variants:
 *   - "plain"   : aged parchment rectangle with a hairline border
 *   - "deckle"  : torn-paper edges via SVG mask (no border; relies on tone)
 *   - "sealed"  : rune-corner flourishes + optional wax-seal in corner
 *
 * Tone:
 *   - "default" : ink-page-aged
 *   - "bright"  : lighter (ink-page-rune-glow) — for hero / spotlight
 *   - "deep"    : page-shadow — for nested, quieter panels
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
    deckle: 'deckle-edge rounded-none',
    sealed: 'border border-ink-page-shadow rounded-xl',
  }[variant];

  const base =
    'relative p-5 shadow-[0_1px_0_0_var(--color-ink-page-rune-glow)_inset,0_4px_14px_-8px_rgba(45,31,21,0.35)]';

  return (
    <Tag
      ref={ref}
      className={`${base} ${toneClasses} ${variantClasses} ${className}`}
      {...props}
    >
      {flourish && <CornerFlourishes />}
      {seal && <WaxSeal position={seal === true ? 'top-right' : seal} />}
      {children}
    </Tag>
  );
});

function CornerFlourishes() {
  return (
    <>
      <img
        src="/glyphs/flourish-corner.svg"
        alt=""
        aria-hidden="true"
        className="absolute top-1 left-1 w-8 h-8 text-ink-secondary opacity-50 pointer-events-none"
        style={{ filter: 'sepia(1) saturate(0.6) brightness(0.6)' }}
      />
      <img
        src="/glyphs/flourish-corner.svg"
        alt=""
        aria-hidden="true"
        className="absolute top-1 right-1 w-8 h-8 opacity-50 pointer-events-none scale-x-[-1]"
        style={{ filter: 'sepia(1) saturate(0.6) brightness(0.6)' }}
      />
      <img
        src="/glyphs/flourish-corner.svg"
        alt=""
        aria-hidden="true"
        className="absolute bottom-1 left-1 w-8 h-8 opacity-50 pointer-events-none scale-y-[-1]"
        style={{ filter: 'sepia(1) saturate(0.6) brightness(0.6)' }}
      />
      <img
        src="/glyphs/flourish-corner.svg"
        alt=""
        aria-hidden="true"
        className="absolute bottom-1 right-1 w-8 h-8 opacity-50 pointer-events-none scale-x-[-1] scale-y-[-1]"
        style={{ filter: 'sepia(1) saturate(0.6) brightness(0.6)' }}
      />
    </>
  );
}

function WaxSeal({ position = 'top-right' }) {
  const positions = {
    'top-right': 'top-2 right-2',
    'top-left': 'top-2 left-2',
    'bottom-right': 'bottom-2 right-2',
    'bottom-left': 'bottom-2 left-2',
  };
  return (
    <img
      src="/glyphs/wax-seal.svg"
      alt=""
      aria-hidden="true"
      className={`absolute ${positions[position] || positions['top-right']} w-10 h-10 drop-shadow-md pointer-events-none`}
    />
  );
}

export default ParchmentCard;
