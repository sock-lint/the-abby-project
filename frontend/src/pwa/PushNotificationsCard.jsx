import { BellRing, BellOff } from 'lucide-react';
import ParchmentCard from '../components/journal/ParchmentCard';
import Button from '../components/Button';
import ErrorAlert from '../components/ErrorAlert';
import { usePushNotifications } from './usePushNotifications';

/**
 * PushNotificationsCard — Settings toggle for out-of-app notifications.
 *
 * The whole economy is kid-submits → parent-approves → kid-collects, and a
 * closed app can't move it: submissions sat unseen until someone thought to
 * check. This is the opt-in that lets an approval request reach a phone.
 *
 * Renders nothing when the server has no VAPID keypair — offering a button
 * that cannot work is worse than staying quiet.
 */
export default function PushNotificationsCard() {
  const {
    supported, enabled, subscribed, permission, busy, error, loading,
    subscribe, unsubscribe,
  } = usePushNotifications();

  // Server can't send: no keypair configured. Nothing useful to offer.
  if (loading || !enabled) return null;

  const blocked = permission === 'denied';

  return (
    <ParchmentCard className="space-y-3">
      <div className="flex items-start gap-3">
        <span className="text-sheikah-teal-deep shrink-0 mt-0.5">
          {subscribed ? <BellRing size={20} /> : <BellOff size={20} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-display text-lg text-ink-primary">
            Notifications on this device
          </div>
          <p className="font-body text-caption text-ink-secondary mt-1">
            {subscribed
              ? 'This device buzzes when something needs you — an approval, a decision on your work, a print finishing.'
              : 'Get a nudge when something needs you, even with the app closed.'}
          </p>
        </div>
      </div>

      <ErrorAlert message={error} />

      {!supported && (
        <p className="font-script text-caption text-ink-whisper">
          This browser can&apos;t do notifications. On an iPhone, add the app to
          your Home Screen first — Safari only allows them for installed apps.
        </p>
      )}

      {supported && blocked && !subscribed && (
        <p className="font-script text-caption text-ink-whisper">
          Notifications are blocked for this site. Turn them back on in your
          browser&apos;s site settings, then come back here.
        </p>
      )}

      {supported && !blocked && (
        subscribed ? (
          <Button variant="secondary" onClick={unsubscribe} disabled={busy} className="w-full">
            {busy ? 'Turning off…' : 'Turn off on this device'}
          </Button>
        ) : (
          <Button onClick={subscribe} disabled={busy} className="w-full">
            {busy ? 'Turning on…' : 'Turn on notifications'}
          </Button>
        )
      )}

      <p className="font-script text-tiny text-ink-whisper">
        Each device opts in separately — turning this on here doesn&apos;t
        change your other phones or tablets.
      </p>
    </ParchmentCard>
  );
}
