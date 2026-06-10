import { Share2 } from 'lucide-react';
import Button from './Button';

/**
 * ShareButton — thin wrapper over the Web Share API for celebration
 * moments (badge earns, sketchbook pieces). Renders nothing when
 * `navigator.share` is unavailable (most desktop browsers), so call
 * sites can mount it unconditionally.
 *
 * `url` is only included when explicitly passed — media URLs in this app
 * are presigned and expire, and the SPA's own routes aren't reachable
 * outside the household, so a text-only payload is usually right.
 * A dismissed share sheet rejects with AbortError; that's a user choice,
 * not an error, so it's swallowed.
 */
export default function ShareButton({ title, text, url, className = '', children }) {
  if (typeof navigator === 'undefined' || typeof navigator.share !== 'function') {
    return null;
  }

  const handleShare = async (e) => {
    e.stopPropagation();
    const payload = { title, text };
    if (url) payload.url = url;
    try {
      await navigator.share(payload);
    } catch {
      // Share sheet dismissed — nothing to do.
    }
  };

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={handleShare}
      className={`flex items-center gap-1 ${className}`}
    >
      <Share2 size={14} aria-hidden="true" />
      {children ?? 'Share'}
    </Button>
  );
}
