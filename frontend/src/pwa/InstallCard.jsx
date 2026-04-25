import { Smartphone, Share } from 'lucide-react';
import ParchmentCard from '../components/journal/ParchmentCard';
import Button from '../components/Button';
import { useInstallPrompt } from './useInstallPrompt';

function isIosSafari() {
  if (typeof window === 'undefined') return false;
  const ua = window.navigator.userAgent;
  return /iPhone|iPad|iPod/.test(ua) && /Safari/.test(ua) && !/CriOS|FxiOS/.test(ua);
}

/**
 * InstallCard — a Settings page card that handles PWA install across the
 * three relevant cases:
 *   1. Already installed → render nothing
 *   2. Chrome/Edge/Android with captured beforeinstallprompt → button
 *   3. iOS Safari (which never fires beforeinstallprompt) → instructions
 *   4. Anything else → soft fallback message
 */
export default function InstallCard() {
  const { canInstall, install, isStandalone } = useInstallPrompt();

  if (isStandalone) return null;

  return (
    <ParchmentCard tone="default" className="flex flex-col gap-3 p-5">
      <div className="flex items-center gap-2">
        <Smartphone size={18} className="text-ink-secondary" aria-hidden="true" />
        <h2 className="font-display text-lede text-ink-primary">Install Abby</h2>
      </div>
      <p className="font-body text-caption text-ink-secondary">
        Get faster access from your home screen — works just like a real app.
      </p>

      {canInstall && (
        <div>
          <Button
            variant="primary"
            size="md"
            onClick={() => {
              install();
            }}
          >
            Install app
          </Button>
        </div>
      )}

      {!canInstall && isIosSafari() && (
        <div className="flex items-start gap-2 rounded-md border border-ink-whisper/30 bg-ink-page-aged/40 px-3 py-2 text-caption text-ink-secondary">
          <Share size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            On iPhone: tap <strong>Share</strong>, then <strong>Add to Home Screen</strong>.
          </span>
        </div>
      )}

      {!canInstall && !isIosSafari() && (
        <p className="text-caption text-ink-whisper italic">
          Your browser doesn&apos;t support installing this app yet — try Chrome or Edge on Android, or Safari on iOS.
        </p>
      )}
    </ParchmentCard>
  );
}
