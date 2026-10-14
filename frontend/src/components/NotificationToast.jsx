import usePrefersReducedMotion from '../hooks/usePrefersReducedMotion';
import { forwardRef } from 'react';
import { motion } from 'framer-motion';
import { X } from 'lucide-react';
import IconButton from './IconButton';
import { RARITY_SOLID_COLORS } from '../constants/colors';
import { swipeToDismiss } from './toastSwipe';

const TONES = new Set(['neutral', 'success', 'danger', 'info', 'growth', 'treasure']);

/** Shared notification presentation. Status tones use opaque cover surfaces;
 * earned rarity uses the existing fixed rarity palette. Polling, receipts,
 * timers and navigation remain with each owning stack.
 */
const NotificationToast = forwardRef(function NotificationToast({
  tone = 'neutral', rarity, icon, title, message, onDismiss, children,
  className = '', swipe = true, ...rest
}, ref) {
  const reducedMotion = usePrefersReducedMotion();
  const rarityClass = rarity && (RARITY_SOLID_COLORS[rarity] || RARITY_SOLID_COLORS.common);
  const toneClass = TONES.has(tone) ? tone : 'neutral';
  return <motion.div
    ref={ref}
    layout={!reducedMotion}
    initial={reducedMotion ? false : { x: 300, opacity: 0 }}
    animate={reducedMotion ? { opacity: 1 } : { x: 0, opacity: 1 }}
    exit={reducedMotion ? { opacity: 0 } : { x: 300, opacity: 0 }}
    transition={reducedMotion ? { duration: 0 } : { type: 'spring', damping: 22, stiffness: 260 }}
    {...(swipe && onDismiss ? swipeToDismiss(onDismiss, reducedMotion) : {})}
    data-notification-tone={toneClass}
    data-notification-rarity={rarity || undefined}
    className={`notification-surface notification-${toneClass} flex items-start gap-3 rounded-lg border px-3 py-2 shadow-lg ${rarityClass || ''} ${className}`}
    {...rest}
  >
    {icon && <span aria-hidden="true" className="shrink-0 mt-0.5 flex items-center">{icon}</span>}
    {(title || message) ? <div className="flex-1 min-w-0 break-words">
      {title && <div className="text-caption font-semibold">{title}</div>}
      {message && <div className="text-caption line-clamp-2">{message}</div>}
      {children}
    </div> : children}
    {onDismiss && <IconButton
      onClick={(event) => { event.stopPropagation(); onDismiss(); }}
      variant="ghost" size="sm" aria-label="Dismiss notification"
      data-notification-dismiss="true" className="shrink-0"
    ><X size={14} aria-hidden="true" /></IconButton>}
  </motion.div>;
});

export default NotificationToast;
