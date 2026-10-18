import { useState } from 'react';
import { resolveAchievementCardImage } from '../../avatar/achievementCardKit';
import './achievement-card.css';

function IconImage({ image, label, size, className, fallback }) {
  const [failed, setFailed] = useState(false);
  return <span className={`achievement-card-icon ${className}`} data-achievement-card-icon={image.assetId}
    style={{ width: size, height: size }} role={label ? 'img' : undefined}
    aria-label={label || undefined} aria-hidden={label ? undefined : true}>
    {failed ? fallback : <img src={image.url} width={image.width} height={image.height} alt=""
      onError={() => setFailed(true)} />}
  </span>;
}

/** Explicit illustrations for page/context use. These are not badge/catalog
 * bindings; keep existing identity artwork when rendering saved items. */
export default function AchievementCardIcon({ icon, size = 40, label = '', className = '', fallback = null }) {
  const image = ['book', 'heart', 'compass'].includes(icon)
    ? resolveAchievementCardImage(`abby-icon-${icon}`, 'icon-512') : null;
  if (!['book', 'heart', 'compass'].includes(icon)) return fallback;
  if (!image) return <span className={`achievement-card-icon ${className}`}
    data-achievement-card-icon={`abby-icon-${icon}`} style={{ width: size, height: size }}
    role={label ? 'img' : undefined} aria-label={label || undefined} aria-hidden={label ? undefined : true}>{fallback}</span>;
  return <IconImage key={image.url} image={image} label={label} size={size} className={className} fallback={fallback} />;
}
