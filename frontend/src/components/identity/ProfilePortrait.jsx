import { useState, useSyncExternalStore } from 'react';
import { PORTRAIT_FRAME_BINDINGS, resolvePortraitFrameImage } from '../../avatar/portraitFrameKit';
import PortraitOrnament from './PortraitOrnament';
import { portraitFrame } from './portraitFrames';
import './identity.css';

const SIZES = { xs: 32, sm: 40, md: 64, lg: 96 };

function readDensity() { return globalThis.devicePixelRatio || 1; }
function serverDensity() { return 1; }
function subscribeDensity(onChange) {
  let resolution;
  const listen = () => {
    resolution?.removeEventListener?.('change', update);
    resolution = globalThis.matchMedia?.(`(resolution: ${readDensity()}dppx)`);
    resolution?.addEventListener?.('change', update);
  };
  const update = () => { listen(); onChange(); };
  globalThis.addEventListener?.('resize', update);
  listen();
  return () => {
    globalThis.removeEventListener?.('resize', update);
    resolution?.removeEventListener?.('change', update);
  };
}

/** One bounded portrait footprint in navigation, profile and maker signatures.
 * Ornament is decorative; ownership and selection remain with the caller. */
export default function ProfilePortrait({ name = '', avatar, frame, size = 'md', imageAlt, className = '', devicePixelRatio }) {
  const [failedUrls, setFailedUrls] = useState(() => new Set());
  const [loadedOverlays, setLoadedOverlays] = useState(() => new Set());
  const [failedOverlays, setFailedOverlays] = useState(() => new Set());
  const browserDensity = useSyncExternalStore(subscribeDensity, readDensity, serverDensity);
  const displayName = name.trim();
  const initial = Array.from(displayName)[0]?.toLocaleUpperCase() || '?';
  const pixels = typeof size === 'number' && size > 0 ? size : SIZES[size] || SIZES.md;
  const label = imageAlt ?? (displayName ? `${displayName}'s profile picture` : 'Your profile picture');
  const decorative = imageAlt === '';
  // Older compact profile responses carry the exact catalog icon, without a
  // slug. Display names alone never select a private artwork identity.
  const frameSlug = frame?.slug ?? Object.entries(PORTRAIT_FRAME_BINDINGS)
    .find(([, assetId]) => assetId === frame?.catalog_icon)?.[0];
  const { family, color } = portraitFrame(frameSlug ? { ...frame, slug: frameSlug } : frame);
  const overlay = resolvePortraitFrameImage(frameSlug, pixels, devicePixelRatio ?? browserDensity);
  const overlayFailed = !!overlay && failedOverlays.has(overlay.url);
  const overlayReady = !!overlay && loadedOverlays.has(overlay.url) && !overlayFailed;

  return <span
    className={`profile-portrait ${overlay ? 'profile-portrait--kit' : ''} ${className}`}
    data-frame-style={family}
    data-portrait-frame={family}
    role={decorative ? undefined : 'img'}
    aria-hidden={decorative || undefined}
    aria-label={decorative ? undefined : `${label}${frame?.name ? ` with ${frame.name}` : ''}`}
    style={{ '--portrait-size': `${pixels}px`, '--portrait-accent': color }}
  >
    <span className="profile-portrait__image" aria-hidden="true">
      {avatar && !failedUrls.has(avatar)
        ? <img src={avatar} alt={imageAlt || ''} onError={() => setFailedUrls((previous) => new Set(previous).add(avatar))} />
        : <span className="profile-portrait__initial">{initial}</span>}
    </span>
    {overlay && !overlayFailed && <img
      key={overlay.url}
      className="profile-portrait__overlay"
      data-portrait-overlay={overlay.assetId}
      data-portrait-variant={overlay.variantId}
      src={overlay.url}
      width={overlay.width}
      height={overlay.height}
      alt=""
      aria-hidden="true"
      decoding="async"
      draggable={false}
      hidden={!overlayReady}
      onLoad={() => setLoadedOverlays((previous) => new Set(previous).add(overlay.url))}
      onError={() => setFailedOverlays((previous) => new Set(previous).add(overlay.url))}
    />}
    {!overlayReady && family !== 'plain' && <PortraitOrnament family={family} />}
  </span>;
}
