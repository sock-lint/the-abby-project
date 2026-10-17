import { useState } from 'react';
import { resolvePedestalImage } from './pedestalRelease';
import './card-ui.css';

function ImageCanvas({ image, alt, className, fallback }) {
  const [state, setState] = useState('loading');
  return (
    <span className={`mt-image-shell ${className}`} data-pedestal-image={image.assetId} data-image-variant={image.variantId} data-image-state={state}>
      {state !== 'error' && <img
        className="mt-image"
        src={image.url}
        alt={alt}
        width={image.width}
        height={image.height}
        loading="lazy"
        decoding="async"
        onLoad={() => setState('ready')}
        onError={() => setState('error')}
      />}
      {state !== 'ready' && <span
        className="mt-image-placeholder text-caption text-ink-secondary bg-ink-page-shadow/20"
        aria-hidden={alt ? undefined : true}
        role={state === 'error' && alt ? 'img' : undefined}
        aria-label={state === 'error' && alt ? alt : undefined}
      >{fallback ?? (alt ? (state === 'loading' ? 'Loading artwork…' : 'Artwork unavailable') : '✦')}</span>}
    </span>
  );
}

/** Whole PNG canvases retain their transparent margins. Artwork never supplies
 * catalog identity or entitlement. URL-keyed state lets a new release recover. */
export default function PedestalImage({ assetId, variantId = 'web', alt = '', className = '', staged, fallback }) {
  const image = resolvePedestalImage(assetId, variantId, staged);
  if (!image) return <span
    className={`mt-image-shell mt-image-placeholder text-caption text-ink-secondary bg-ink-page-shadow/20 ${className}`}
    data-pedestal-image={assetId}
    data-image-state="unavailable"
    role={alt ? 'img' : undefined}
    aria-label={alt || undefined}
    aria-hidden={alt ? undefined : true}
  >{fallback ?? (alt ? 'Artwork unavailable' : '✦')}</span>;
  return <ImageCanvas key={image.url} image={image} alt={alt} className={className} fallback={fallback} />;
}
