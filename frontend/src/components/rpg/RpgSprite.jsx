import { useSpriteCatalog } from '../../providers/SpriteCatalogProvider';

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
 * Renders an RPG entity icon. Branches on sprite metadata:
 *  - static (frames=1): plain <img>
 *  - animated (frames>1): <span> with CSS background-position animation
 *  - unknown slug or catalog still loading: emoji fallback
 */
export default function RpgSprite({
  spriteKey,
  icon,
  size = 32,
  className = '',
  alt = '',
}) {
  const { getSpriteMeta } = useSpriteCatalog();
  const meta = getSpriteMeta(spriteKey);

  if (meta && meta.frames === 1) {
    return (
      <img
        src={meta.url}
        alt={alt || spriteKey || 'sprite'}
        width={size}
        height={size}
        style={{ imageRendering: 'pixelated', width: size, height: size }}
        className={className}
      />
    );
  }

  if (meta && meta.frames > 1) {
    const duration = (meta.frames / meta.fps).toFixed(3);
    const totalWidth = meta.frames * size;
    // Canonical sprite-sheet animation: endX is -N × size (off-sheet,
    // transparent) and `steps(N)` (= jump-end) holds each of the N frames
    // for 1/N of the duration. At t=1 the animation jumps to endX but
    // immediately loops back to 0, so the off-sheet position is never
    // visible. The previous `steps(N, jump-none)` + endX=-(N-1)×size
    // technique held only the first N-1 frames for 1/(N-1) duration
    // each and flashed frame N-1 briefly at the loop boundary — which
    // looked to users like a bleed/ghosting artifact.
    const endX = -meta.frames * size;
    return (
      <span
        role="img"
        aria-label={alt || spriteKey || 'sprite'}
        className={`inline-block ${className}`}
        style={{
          width: size,
          height: size,
          backgroundImage: `url(${meta.url})`,
          backgroundSize: `${totalWidth}px ${size}px`,
          backgroundPositionX: 0,
          imageRendering: 'pixelated',
          '--sprite-end-x': `${endX}px`,
          animation: `sprite-cycle ${duration}s steps(${meta.frames}) infinite`,
        }}
      />
    );
  }

  // Emoji fallback
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
