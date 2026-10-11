import { useState, useEffect, useRef, useId } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell, BellRing } from 'lucide-react';
import { markAllRead as markAllReadApi, markNotificationRead } from '../api';
import { usePulse } from '../providers/pulseContext';
import { formatDate } from '../utils/format';
import IconButton from './IconButton';
import BottomSheet from './BottomSheet';
import Button from './Button';
import useIsDesktop from '../hooks/useIsDesktop';
import { metaForNotification } from './notifications.constants';

// Mirror the unread count onto the installed-PWA home-screen icon
// (Badging API — Android + iOS 16.4+ standalone; a no-op everywhere else).
function syncAppBadge(count) {
  try {
    if (count > 0) navigator.setAppBadge?.(count)?.catch?.(() => {});
    else navigator.clearAppBadge?.()?.catch?.(() => {});
  } catch { /* unsupported — in-app bell still shows the count */ }
}

export default function NotificationBell() {
  const { pulse, refresh } = usePulse();
  // Seeded from the shared heartbeat, then mutated locally on read so a tap
  // feels instant; the next beat reconciles.
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState([]);
  const [open, setOpen] = useState(false);
  const [markAllError, setMarkAllError] = useState('');
  const ref = useRef(null);
  const triggerRef = useRef(null);
  const popoverId = useId();
  const navigate = useNavigate();
  const isDesktop = useIsDesktop();


  const handleNotificationClick = async (notification) => {
    if (!notification.is_read) {
      try {
        await markNotificationRead(notification.id);
        setNotifications(prev =>
          prev.map(n => n.id === notification.id ? { ...n, is_read: true } : n)
        );
        const next = Math.max(0, unreadCount - 1);
        setUnreadCount(next);
        syncAppBadge(next);
      } catch { /* network errors here are non-fatal */ }
    }
    const { defaultRoute } = metaForNotification(notification);
    const target = notification.link || defaultRoute;
    if (target) {
      setOpen(false);
      navigate(target);
    }
  };

  // Clear optimistically so the tap feels instant, then roll the whole view
  // back if the request never lands. Without the catch a failed call left the
  // button looking like a dead no-op — badge still lit, nothing said.
  const handleMarkAllRead = async () => {
    const prevCount = unreadCount;
    const prevNotifications = notifications;
    setMarkAllError('');
    setUnreadCount(0);
    syncAppBadge(0);
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
    try {
      await markAllReadApi();
    } catch {
      setUnreadCount(prevCount);
      syncAppBadge(prevCount);
      setNotifications(prevNotifications);
      setMarkAllError("Couldn't mark those read — check your connection and try again.");
    }
  };

  const markAllBanner = markAllError ? (
    <p role="alert" className="text-caption text-ember-deep">
      {markAllError}
    </p>
  ) : null;

  // Both the count and the list ride the shared heartbeat now — the bell used
  // to run its own 30s timer (one that never paused on a backgrounded tab)
  // and a second fetch every time the dropdown opened.
  useEffect(() => {
    if (!pulse) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- syncing local view state to each new heartbeat
    setUnreadCount(pulse.unread_count ?? 0);
    setNotifications(Array.isArray(pulse.notifications) ? pulse.notifications : []);
    syncAppBadge(pulse.unread_count ?? 0);
  }, [pulse]);

  useEffect(() => {
    // Only the desktop popover dismisses on an outside click — the mobile
    // sheet portals outside this ref and owns its own close paths, so this
    // listener would slam it shut on the first tap inside it.
    if (!isDesktop) return undefined;
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [isDesktop]);

  // One list, two shells: a thumb-reachable sheet on phones, the desktop
  // popover at md+.
  const listBody = (
    notifications.length === 0 ? (
      <div
        role="status"
        className="p-5 text-center text-body text-ink-whisper flex flex-col items-center gap-1"
      >
        <BellRing size={20} aria-hidden="true" className="text-ink-whisper/70" />
        <span className="font-display italic text-ink-secondary">All caught up</span>
        <span className="font-script text-tiny">no new notifications</span>
      </div>
    ) : (
      notifications.slice(0, 20).map((n) => {
        const { Icon, accentClass, defaultRoute } = metaForNotification(n);
        const clickable = Boolean(n.link || defaultRoute);
        // intentional: native row button keeps the edge-to-edge list styling;
        // no-link rows still invoke the existing mark-read action.
        return (
          <button
            key={n.id}
            type="button"
            aria-label={n.message ? `${n.title}: ${n.message}` : n.title}
            onClick={() => handleNotificationClick(n)}
            className={`block w-full min-h-11 text-left p-3 border-b border-ink-page-shadow/50 last:border-0 transition-colors focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sheikah-teal ${
              !n.is_read ? 'bg-amber-primary/5' : ''
            } ${clickable ? 'cursor-pointer hover:bg-ink-page-shadow/30' : ''}`}
          >
            <span className="flex items-start gap-2">
              {!n.is_read && (
                <span aria-hidden="true" className="w-2 h-2 bg-amber-primary rounded-full mt-1.5 shrink-0" />
              )}
              <Icon
                size={16}
                aria-hidden="true"
                className={`mt-0.5 shrink-0 ${accentClass}`}
              />
              <span className="min-w-0 flex-1 break-words">
                <span className="block text-body font-medium">{n.title}</span>
                {n.message && (
                  <span className="block text-caption text-ink-whisper mt-0.5">{n.message}</span>
                )}
                <span className="block text-micro text-ink-whisper mt-1">
                  {formatDate(n.created_at)}
                </span>
              </span>
            </span>
          </button>
        );
      })
    )
  );

  return (
    <div
      className="relative"
      ref={ref}
      onKeyDown={(event) => {
        if (isDesktop && open && event.key === 'Escape') {
          event.preventDefault();
          event.stopPropagation();
          setOpen(false);
          triggerRef.current?.focus({ preventScroll: true });
        }
      }}
      onBlur={(event) => {
        if (isDesktop && open && event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) {
          setOpen(false);
        }
      }}
    >
      <IconButton
        ref={triggerRef}
        onClick={() => { if (!open) { refresh(); setMarkAllError(''); } setOpen(!open); }}
        variant="ghost"
        aria-label={unreadCount > 0 ? `Notifications (${unreadCount} unread)` : 'Notifications'}
        aria-expanded={open}
        aria-haspopup={!isDesktop ? 'dialog' : undefined}
        aria-controls={isDesktop && open ? popoverId : undefined}
        className="relative hover:bg-ink-page-shadow/60"
      >
        <Bell size={18} aria-hidden="true" className="text-ink-whisper" />
        {unreadCount > 0 && (
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            aria-hidden="true"
            className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-ember-deep rounded-full text-micro text-ink-page flex items-center justify-center font-bold"
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </motion.span>
        )}
      </IconButton>

      {!isDesktop && open && (
        <BottomSheet title="Notifications" onClose={() => setOpen(false)}>
          {unreadCount > 0 && (
            <Button variant="secondary" size="sm" onClick={handleMarkAllRead} className="w-full">
              Mark all read
            </Button>
          )}
          {markAllBanner}
          {/* Bleed to the sheet's edges so rows are full-width tap targets. */}
          <div className="-mx-4">{listBody}</div>
        </BottomSheet>
      )}

      <AnimatePresence>
        {isDesktop && open && (
          <motion.div
            id={popoverId}
            role="region"
            aria-label="Notifications"
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            className="absolute right-0 top-full mt-2 w-80 max-w-[calc(100vw-2rem)] max-h-[min(24rem,calc(100dvh-8rem))] flex flex-col bg-ink-page-aged border border-ink-page-shadow rounded-2xl shadow-xl overflow-hidden z-50"
          >
            <div className="flex items-center justify-between gap-2 p-3 border-b border-ink-page-shadow shrink-0">
              <span className="font-display font-bold text-body">Notifications</span>
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={handleMarkAllRead}
                  className="min-h-11 px-2 rounded-xl text-caption text-sheikah-teal-deep hover:bg-sheikah-teal/10"
                >
                  Mark all read
                </button>
              )}
            </div>
            {markAllError && (
              <div className="px-3 py-2 border-b border-ink-page-shadow shrink-0">{markAllBanner}</div>
            )}
            <div className="min-h-0 overflow-y-auto overscroll-contain">{listBody}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
