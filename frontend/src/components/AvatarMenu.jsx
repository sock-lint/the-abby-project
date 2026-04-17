import { useState, useEffect, useRef } from 'react';
import { NavLink } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { DragonIcon } from './icons/JournalIcons';

/**
 * AvatarMenu — the user's avatar circle doubling as a "my profile" dropdown.
 *
 * Two call sites today:
 *   - JournalShell mobile header     → <AvatarMenu user={user} compact />
 *   - ChapterNav desktop sidebar     → <AvatarMenu user={user} align="top" />
 *
 * The menu is intentionally sparse — a single Sigil link today, with room to
 * grow (Settings, Sign off, etc.) without redesign.
 */
export default function AvatarMenu({ user, compact = false, align = 'bottom' }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const handleKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  const initial = (user?.display_name || user?.username || '?')[0].toUpperCase();
  const circleSize = compact ? 'w-9 h-9 text-sm' : 'w-8 h-8 text-sm';
  // Anchor: desktop sidebar footer (full-width trigger) → right-align so the
  // menu hugs the rail. Mobile header (trigger pinned top-left) → left-align
  // so the menu doesn't run off-screen.
  const horizontalAnchor = compact ? 'left-0' : 'right-0';
  const verticalAnchor =
    align === 'top' ? 'bottom-full mb-2' : 'top-full mt-2';
  const menuPos = `${verticalAnchor} ${horizontalAnchor}`;
  const menuInitialY = align === 'top' ? 6 : -6;

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Open profile menu"
        className={`flex items-center gap-2 min-w-0 rounded-lg transition-colors
                    ${compact ? 'pr-2' : 'w-full px-2 py-1'}
                    hover:bg-sheikah-teal/10 focus-visible:outline-none
                    focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep/50`}
      >
        <span
          className={`${circleSize} rounded-full bg-sheikah-teal/20 border
                      border-sheikah-teal/40 flex items-center justify-center
                      text-sheikah-teal-deep font-rune shrink-0 transition-colors
                      ${open ? 'bg-sheikah-teal/35 border-sheikah-teal-deep' : ''}`}
        >
          {initial}
        </span>
        <span className="text-sm font-body min-w-0 text-left">
          <span className="block text-ink-primary truncate leading-tight">
            {user?.display_name || user?.username}
          </span>
          <span className="block font-script text-ink-whisper text-xs capitalize leading-tight">
            {user?.role}
          </span>
        </span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            initial={{ opacity: 0, y: menuInitialY, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: menuInitialY, scale: 0.98 }}
            transition={{ duration: 0.14, ease: 'easeOut' }}
            className={`absolute ${menuPos} w-60 bg-ink-page-aged border border-ink-page-shadow
                        rounded-xl shadow-xl overflow-hidden z-50
                        shadow-[0_0_0_1px_var(--color-sheikah-teal-deep)_inset,0_8px_24px_rgba(0,0,0,0.18)]`}
          >
            {/* Menu header — reads as "you are …" so the menu feels like a profile drawer */}
            <div className="px-4 pt-3 pb-2 border-b border-ink-page-shadow/70 bg-ink-page/40">
              <div className="font-script text-ink-whisper text-tiny uppercase tracking-[0.2em]">
                you are
              </div>
              <div className="font-display italic text-base text-ink-primary leading-tight truncate">
                {user?.display_name || user?.username || 'adventurer'}
              </div>
              <div className="font-script text-sheikah-teal-deep text-xs capitalize leading-tight mt-0.5">
                {user?.role || 'traveler'}
              </div>
            </div>

            {/* Menu links — currently just Sigil, but the block leaves room to grow */}
            <nav className="p-2" role="none">
              <NavLink
                to="/sigil"
                role="menuitem"
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  `group flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all
                   ${isActive
                      ? 'bg-sheikah-teal/15 text-ink-primary'
                      : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/60'
                   }`
                }
              >
                <DragonIcon size={20} className="text-sheikah-teal-deep shrink-0" />
                <span className="min-w-0">
                  <span className="block font-display text-base tracking-wide leading-tight">
                    Sigil
                  </span>
                  <span className="block font-script text-ink-whisper text-xs leading-tight">
                    who you are
                  </span>
                </span>
              </NavLink>
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
