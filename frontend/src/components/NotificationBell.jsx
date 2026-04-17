import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Bell } from 'lucide-react';
import { getNotifications, getUnreadCount, markAllRead as markAllReadApi, markNotificationRead } from '../api';
import { formatDate } from '../utils/format';
import IconButton from './IconButton';

export default function NotificationBell() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState([]);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const navigate = useNavigate();

  const loadCount = async () => {
    try {
      const data = await getUnreadCount();
      setUnreadCount(data.count);
    } catch { /* network errors here are non-fatal */ }
  };

  const loadNotifications = async () => {
    try {
      const data = await getNotifications();
      setNotifications(data.results || data || []);
    } catch { /* network errors here are non-fatal */ }
  };

  const handleNotificationClick = async (notification) => {
    if (!notification.is_read) {
      try {
        await markNotificationRead(notification.id);
        setNotifications(prev =>
          prev.map(n => n.id === notification.id ? { ...n, is_read: true } : n)
        );
        setUnreadCount(prev => Math.max(0, prev - 1));
      } catch { /* network errors here are non-fatal */ }
    }
    if (notification.link) {
      setOpen(false);
      navigate(notification.link);
    }
  };

  const handleMarkAllRead = async () => {
    await markAllReadApi();
    setUnreadCount(0);
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional polling: kick off the first fetch and refresh every 30s
    loadCount();
    const interval = setInterval(loadCount, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch the list lazily when the dropdown opens
    if (open) loadNotifications();
  }, [open]);

  useEffect(() => {
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <IconButton
        onClick={() => setOpen(!open)}
        variant="ghost"
        aria-label={unreadCount > 0 ? `Notifications (${unreadCount} unread)` : 'Notifications'}
        className="relative hover:bg-ink-page-shadow/60/50"
      >
        <Bell size={18} className="text-ink-whisper" />
        {unreadCount > 0 && (
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 rounded-full text-micro text-white flex items-center justify-center font-bold"
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </motion.span>
        )}
      </IconButton>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            className="absolute right-0 top-full mt-2 w-80 max-h-96 bg-ink-page-aged border border-ink-page-shadow rounded-xl shadow-xl overflow-hidden z-50"
          >
            <div className="flex items-center justify-between p-3 border-b border-ink-page-shadow">
              <span className="font-display font-bold text-sm">Notifications</span>
              {unreadCount > 0 && (
                <button
                  onClick={handleMarkAllRead}
                  className="text-xs text-sheikah-teal-deep hover:underline"
                >
                  Mark all read
                </button>
              )}
            </div>
            <div className="overflow-y-auto max-h-72">
              {notifications.length === 0 ? (
                <div className="p-4 text-center text-sm text-ink-whisper">
                  No notifications
                </div>
              ) : (
                notifications.slice(0, 20).map((n) => (
                  <div
                    key={n.id}
                    onClick={() => handleNotificationClick(n)}
                    className={`p-3 border-b border-ink-page-shadow/50 last:border-0 transition-colors ${
                      !n.is_read ? 'bg-amber-primary/5' : ''
                    } ${n.link ? 'cursor-pointer hover:bg-ink-page-shadow/60/30' : ''}`}
                  >
                    <div className="flex items-start gap-2">
                      {!n.is_read && (
                        <span className="w-2 h-2 bg-amber-primary rounded-full mt-1.5 shrink-0" />
                      )}
                      <div className={!n.is_read ? '' : 'ml-4'}>
                        <div className="text-sm font-medium">{n.title}</div>
                        {n.message && (
                          <div className="text-xs text-ink-whisper mt-0.5">{n.message}</div>
                        )}
                        <div className="text-micro text-ink-whisper mt-1">
                          {formatDate(n.created_at)}
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
