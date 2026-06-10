import { useEffect, useState } from 'react';
import { WifiOff } from 'lucide-react';

/**
 * OfflineBanner — sticky strip shown while the browser reports no
 * connectivity. Pairs with the Workbox NetworkFirst runtime cache in
 * vite.config.js: reads render from the last saved copy, so the banner's
 * job is to explain why content may be stale and that writes won't save.
 * Listens to the online/offline window events; renders nothing online.
 */
export default function OfflineBanner() {
  const [offline, setOffline] = useState(
    typeof navigator !== 'undefined' && navigator.onLine === false,
  );

  useEffect(() => {
    const goOffline = () => setOffline(true);
    const goOnline = () => setOffline(false);
    window.addEventListener('offline', goOffline);
    window.addEventListener('online', goOnline);
    return () => {
      window.removeEventListener('offline', goOffline);
      window.removeEventListener('online', goOnline);
    };
  }, []);

  if (!offline) return null;

  return (
    <div
      role="status"
      className="sticky top-0 z-30 bg-ember-deep text-ink-page-rune-glow px-4 py-2 text-body flex items-center gap-2"
    >
      <WifiOff size={16} aria-hidden="true" className="shrink-0" />
      <span className="font-body">
        You&apos;re offline — showing the last saved copy. Changes won&apos;t
        save until you&apos;re back.
      </span>
    </div>
  );
}
