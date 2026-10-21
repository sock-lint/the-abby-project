import { useState } from 'react';
import PortraitOrnament from './PortraitOrnament';
import { portraitFrame } from './portraitFrames';
import './identity.css';

const SIZES = { xs: 32, sm: 40, md: 64, lg: 80 };

/** One bounded portrait footprint in navigation, profile and maker signatures.
 * Ornament is decorative; ownership and selection remain with the caller. */
export default function ProfilePortrait({ name = '', avatar, frame, size = 'md', imageAlt, className = '' }) {
  const [failedUrls, setFailedUrls] = useState(() => new Set());
  const { family, color } = portraitFrame(frame);
  const displayName = name.trim();
  const initial = Array.from(displayName)[0]?.toLocaleUpperCase() || '?';
  const pixels = typeof size === 'number' && size > 0 ? size : SIZES[size] || SIZES.md;
  const label = imageAlt ?? (displayName ? `${displayName}'s profile picture` : 'Your profile picture');
  const decorative = imageAlt === '';

  return <span
    className={`profile-portrait ${className}`}
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
    {family !== 'plain' && <PortraitOrnament family={family} />}
  </span>;
}
