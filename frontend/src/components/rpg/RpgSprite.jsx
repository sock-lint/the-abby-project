import { getSpriteUrl } from '../../assets/rpg-sprites';

const SIZE_TO_TEXT_CLASS = {
  24: 'text-xl',
  32: 'text-2xl',
  40: 'text-3xl',
  48: 'text-4xl',
  56: 'text-5xl',
  64: 'text-6xl',
  80: 'text-7xl',
  96: 'text-8xl',
};

/**
 * Renders an RPG entity icon. Prefers a bundled pixel-art sprite when
 * `spriteKey` resolves to a known asset; otherwise falls back to the
 * emoji `icon` string sized by `size` (in px).
 */
export default function RpgSprite({
  spriteKey,
  icon,
  size = 32,
  className = '',
  alt = '',
}) {
  const url = getSpriteUrl(spriteKey);
  if (url) {
    return (
      <img
        src={url}
        alt={alt || spriteKey || 'sprite'}
        width={size}
        height={size}
        style={{ imageRendering: 'pixelated', width: size, height: size }}
        className={className}
      />
    );
  }
  // Emoji fallback — match the visual size with a Tailwind text class when
  // possible; otherwise use inline font-size.
  const cls = SIZE_TO_TEXT_CLASS[size];
  if (cls) {
    return (
      <span className={`leading-none inline-block ${cls} ${className}`} aria-label={alt}>
        {icon || '✨'}
      </span>
    );
  }
  return (
    <span
      className={`leading-none inline-block ${className}`}
      style={{ fontSize: size }}
      aria-label={alt}
    >
      {icon || '✨'}
    </span>
  );
}
