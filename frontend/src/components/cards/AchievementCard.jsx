import { forwardRef, useState } from 'react';
import { resolveAchievementCardImage } from '../../avatar/achievementCardKit';
import './achievement-card.css';

const CardCanvas = forwardRef(function CardCanvas({
  as: Tag, variant, base, border, className, contentClassName, children, style, ...props
}, ref) {
  const [loaded, setLoaded] = useState({ base: false, border: false });
  const [failed, setFailed] = useState(false);
  const ready = !!base && !!border && loaded.base && loaded.border && !failed;
  const state = !base || !border || failed ? 'unavailable' : ready ? 'ready' : 'pending';

  return (
    <Tag {...props} ref={ref}
      className={`achievement-card ${className}`}
      data-achievement-card={variant} data-achievement-card-art={state}
      style={{ ...style, ...(ready ? {
        '--achievement-card-base': `url(${JSON.stringify(base.url)})`,
        '--achievement-card-border': `url(${JSON.stringify(border.url)})`,
      } : {}) }}>
      {base && border && <>
        {/* Real image loads gate the complete pair. CSS backgrounds alone do
            not report failures; a partial pair must keep the readable fallback. */}
        <img hidden src={base.url} width={base.width} height={base.height} alt=""
          onLoad={() => setLoaded((current) => ({ ...current, base: true }))}
          onError={() => setFailed(true)} />
        <img hidden src={border.url} width={border.width} height={border.height} alt=""
          onLoad={() => setLoaded((current) => ({ ...current, border: true }))}
          onError={() => setFailed(true)} />
      </>}
      {ready && <>
        <span aria-hidden="true" className="achievement-card__layer achievement-card__base" data-achievement-card-layer="base" />
        <span aria-hidden="true" className="achievement-card__layer achievement-card__border" data-achievement-card-layer="border" />
      </>}
      <div className={`achievement-card__content ${contentClassName}`}>{children}</div>
    </Tag>
  );
});

/** Presentation only: the source's matching layers use 64px corner slices;
 * live content can grow freely inside scaled 96px safe insets. */
const AchievementCard = forwardRef(function AchievementCard({
  as = 'div', variant = 'wide', className = '', contentClassName = '', children, ...props
}, ref) {
  const shape = variant === 'tall' ? 'tall' : 'wide';
  const base = resolveAchievementCardImage(`abby-card-base-${shape}`, shape);
  const border = resolveAchievementCardImage(`abby-card-border-gold-${shape}`, shape);
  return <CardCanvas key={`${base?.url || ''}|${border?.url || ''}`} ref={ref}
    {...props} as={as} variant={shape} base={base} border={border}
    className={className} contentClassName={contentClassName}>{children}</CardCanvas>;
});

export default AchievementCard;
