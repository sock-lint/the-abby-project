import { useState } from 'react';
import { resolveCatalogIcon } from '../../catalog/sharedCatalogIcons';
import RpgSprite from './RpgSprite';

/** Static private catalog art is a presentation of an existing server record.
 * A missing binding, private install or failed PNG keeps the original fallback. */
export default function CatalogIcon({ assetId, size = 32, alt = '', className = '', ...fallback }) {
  const [failedUrls, setFailedUrls] = useState(() => new Set());
  const image = resolveCatalogIcon(assetId);
  if (!image || failedUrls.has(image.url)) {
    return <RpgSprite {...fallback} size={size} alt={alt} className={className} />;
  }
  return (
    <img
      key={image.url}
      src={image.url}
      alt={alt}
      width={size}
      height={size}
      loading="lazy"
      onError={() => setFailedUrls((previous) => new Set(previous).add(image.url))}
      style={{ width: size, height: size, objectFit: 'contain', imageRendering: 'auto' }}
      className={className}
    />
  );
}
