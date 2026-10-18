import { useState } from 'react';
import { resolveArtworkImage } from '../../catalog/sharedArtwork';

/** Decorative catalog artwork never selects an identity from its label.
 * Failed URLs retain the caller's complete authored glyph or placeholder. */
export default function ArtworkImage({ assetId, fallback = null, size = 32, className = '' }) {
  const [failedUrls, setFailedUrls] = useState(() => new Set());
  const image = resolveArtworkImage(assetId);
  if (!image || failedUrls.has(image.url)) return fallback;
  return <img key={image.url} src={image.url} alt="" aria-hidden="true"
    data-artwork-image={assetId} width={typeof size === 'number' ? size : undefined}
    height={typeof size === 'number' ? size : undefined} loading="lazy" className={className}
    style={{ width: size, height: size, objectFit: 'contain', imageRendering: 'auto', display: 'inline-block', verticalAlign: 'middle' }}
    onError={() => setFailedUrls((previous) => new Set(previous).add(image.url))} />;
}
