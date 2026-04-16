import { useCallback, useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import RuneBadge from '../journal/RuneBadge';

function slugify(s) {
  return String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function storageKey(title) {
  return `dashboard-accordion-${slugify(title)}`;
}

function readStored(title, fallback) {
  if (typeof window === 'undefined') return fallback;
  try {
    const v = window.localStorage.getItem(storageKey(title));
    if (v === '1') return true;
    if (v === '0') return false;
  } catch { /* ignore */ }
  return fallback;
}

/**
 * AccordionSection — default-collapsed disclosure with a 1-line peek.
 * Persists open state per-title in localStorage so expanded preferences survive.
 *
 * Props:
 *   title      : display title (required)
 *   kicker     : caveat-script line above title
 *   count      : optional numeric badge beside title
 *   peek       : ReactNode shown when closed (single-line summary)
 *   children   : body rendered when open
 *   defaultOpen: fallback when no persisted state exists
 */
export default function AccordionSection({
  title, kicker, count, peek, children, defaultOpen = false,
}) {
  const [open, setOpen] = useState(() => readStored(title, defaultOpen));

  useEffect(() => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(storageKey(title), open ? '1' : '0');
    } catch { /* ignore quota/blocked */ }
  }, [title, open]);

  const toggle = useCallback(() => setOpen((o) => !o), []);

  return (
    <section className="rounded-xl border border-ink-page-shadow bg-ink-page-aged/80">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="w-full flex items-center gap-3 text-left px-4 py-3"
      >
        <div className="flex-1 min-w-0">
          {kicker && (
            <div className="font-script text-sheikah-teal-deep text-xs">{kicker}</div>
          )}
          <div className="flex items-baseline gap-2">
            <h2 className="font-display text-lg md:text-xl text-ink-primary leading-tight truncate">
              {title}
            </h2>
            {count != null && (
              <RuneBadge tone="teal" size="sm">{count}</RuneBadge>
            )}
          </div>
          {!open && peek && (
            <div className="mt-1 font-body text-xs text-ink-secondary truncate">
              {peek}
            </div>
          )}
        </div>
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ type: 'spring', damping: 22, stiffness: 280 }}
          className="text-ink-whisper shrink-0"
        >
          <ChevronDown size={18} />
        </motion.span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 pt-1">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
