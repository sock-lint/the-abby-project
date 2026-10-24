import { useState, useEffect, useRef, useId } from 'react';
import { NavLink } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { BookOpen, History, Settings, SlidersHorizontal } from 'lucide-react';
import { DragonIcon } from './icons/JournalIcons';
import { usePulse } from '../providers/pulseContext';
import IdentitySummary from './identity/IdentitySummary';
import { identityForUser } from './identity/identity';

/**
 * AvatarMenu — the user's avatar circle doubling as a "my profile" dropdown.
 *
 * Two call sites today:
 *   - JournalShell mobile header     → <AvatarMenu user={user} compact />
 *   - ChapterNav desktop sidebar     → <AvatarMenu user={user} align="top" />
 *
 * Menu items: Sigil (profile) + Manage / Activity / Content Catalog
 * (parent-only) + Settings. On mobile the bottom tab bar holds only the six
 * chapters, so the avatar dropdown is the sole mobile entry point to
 * /settings and the parent utility pages.
 *
 * The /codex row is labelled "Content Catalog" to match the page heading:
 * it browses the RPG catalog (items, pet species, grown pets, challenges),
 * separate from the kid-facing Lorebook at /lorebook, and "Codex" already
 * names the Bestiary hub's species tab.
 */
export default function AvatarMenu({ user, compact = false, align = 'bottom', showRecognition = true }) {
  const { pulse } = usePulse();
  const identity = identityForUser(pulse?.identity, user);
  const level = identity ? pulse?.header?.level : null;
  const name = user?.display_name || user?.username || 'Member';
  const role = user?.role ? `${user.role[0].toUpperCase()}${user.role.slice(1)}` : '';
  const details = [role, user?.family?.name].filter(Boolean).join(' · ');
  const [open, setOpen] = useState(false);
  const [showRing] = useState(() => {
    const count = Number(localStorage.getItem('avatar_hint_count') || '0');
    if (count >= 3) return false;
    localStorage.setItem('avatar_hint_count', String(count + 1));
    return true;
  });
  const ref = useRef(null);
  const triggerRef = useRef(null);
  const menuRef = useRef(null);
  const focusLast = useRef(false);
  const menuId = useId();

  const closeMenu = () => {
    setOpen(false);
    triggerRef.current?.focus({ preventScroll: true });
  };

  const handleMenuKeyDown = (event) => {
    const items = Array.from(menuRef.current?.querySelectorAll('[role="menuitem"]') || []);
    const index = items.indexOf(document.activeElement);
    let next;
    if (event.key === 'ArrowDown') next = (index + 1) % items.length;
    else if (event.key === 'ArrowUp') next = (index - 1 + items.length) % items.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = items.length - 1;
    else if (event.key === 'Tab') {
      closeMenu();
      return;
    }
    else if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      closeMenu();
      return;
    } else return;
    event.preventDefault();
    items[next]?.focus();
  };

  useEffect(() => {
    if (!open) return undefined;
    const items = menuRef.current?.querySelectorAll('[role="menuitem"]');
    items?.[focusLast.current ? items.length - 1 : 0]?.focus({ preventScroll: true });
    const handleClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const handleFocus = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('focusin', handleFocus);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('focusin', handleFocus);
    };
  }, [open]);

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
        ref={triggerRef}
        type="button"
        onClick={() => { focusLast.current = false; setOpen((v) => !v); }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            focusLast.current = event.key === 'ArrowUp';
            setOpen(true);
          } else if (event.key === 'Escape' && open) closeMenu();
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label="Open profile menu"
        aria-description={`${name}${Number.isInteger(level) && level >= 0 ? `, Level ${level}` : ''}`}
        className={`flex items-center gap-2 min-h-11 max-w-full rounded-2xl transition-colors
                    ${compact ? 'min-w-11 w-full py-1' : 'min-w-11 w-full px-2 py-1'}
                    hover:bg-sheikah-teal/10 focus-visible:outline-none
                    focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep/50`}
      >
        <IdentitySummary name={name} avatar={user?.avatar} frame={identity?.active_frame}
          title={identity?.active_title} badge={identity?.active_trophy_badge} level={level}
          portraitSize="sm" details={compact ? null : details} showRecognition={showRecognition}
          className={`text-left ${compact ? 'identity-summary--compact' : ''}`}
          portraitClassName={showRing && compact && !identity?.active_frame ? 'rounded-full ring-2 ring-gold-leaf/60 ring-offset-1 ring-offset-ink-page' : ''} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            ref={menuRef}
            id={menuId}
            role="menu"
            aria-label="Profile"
            onKeyDown={handleMenuKeyDown}
            initial={{ opacity: 0, y: menuInitialY, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: menuInitialY, scale: 0.98 }}
            transition={{ duration: 0.14, ease: 'easeOut' }}
            className={`absolute ${menuPos} ${compact ? 'w-60' : 'w-60 lg:w-full'} max-w-[calc(100vw-2rem-env(safe-area-inset-left)-env(safe-area-inset-right))] bg-ink-page-aged border border-ink-page-shadow
                        rounded-2xl shadow-xl overflow-y-auto overflow-x-hidden overscroll-contain z-50
                        max-h-[calc(100dvh-10rem-env(safe-area-inset-top)-env(safe-area-inset-bottom))] lg:max-h-[calc(100dvh-6rem)]
                        shadow-[0_0_0_1px_var(--color-sheikah-teal-deep)_inset,0_8px_24px_rgba(0,0,0,0.18)]`}
          >
            {/* Saved appearance and level match the header and Profile. */}
            <div className="px-4 pt-3 pb-2 border-b border-ink-page-shadow/70 bg-ink-page/40">
              <IdentitySummary as="div" name={name} avatar={user?.avatar} frame={identity?.active_frame}
                title={identity?.active_title} badge={identity?.active_trophy_badge} level={level}
                details={details} />
            </div>

            <nav className="p-2" role="none">
              <NavLink
                to="/sigil"
                role="menuitem"
                tabIndex={-1}
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
                    Profile
                  </span>
                  <span className="block font-script text-ink-whisper text-caption leading-tight">
                    who you are
                  </span>
                </span>
              </NavLink>
              {user?.role === 'parent' && (
                <>
                  <NavLink
                    to="/manage"
                    role="menuitem"
                    tabIndex={-1}
                    onClick={() => setOpen(false)}
                    className={({ isActive }) =>
                      `group flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all
                       ${isActive
                          ? 'bg-sheikah-teal/15 text-ink-primary'
                          : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/60'
                       }`
                    }
                  >
                    <SlidersHorizontal size={20} className="text-sheikah-teal-deep shrink-0" />
                    <span className="min-w-0">
                      <span className="block font-display text-base tracking-wide leading-tight">
                        Manage
                      </span>
                      <span className="block font-script text-ink-whisper text-caption leading-tight">
                        children, templates, family
                      </span>
                    </span>
                  </NavLink>
                  <NavLink
                    to="/activity"
                    role="menuitem"
                    tabIndex={-1}
                    onClick={() => setOpen(false)}
                    className={({ isActive }) =>
                      `group flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all
                       ${isActive
                          ? 'bg-sheikah-teal/15 text-ink-primary'
                          : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/60'
                       }`
                    }
                  >
                    <History size={20} className="text-sheikah-teal-deep shrink-0" />
                    <span className="min-w-0">
                      <span className="block font-display text-base tracking-wide leading-tight">
                        Activity
                      </span>
                      <span className="block font-script text-ink-whisper text-caption leading-tight">
                        recent family log
                      </span>
                    </span>
                  </NavLink>
                  <NavLink
                    to="/codex"
                    role="menuitem"
                    tabIndex={-1}
                    onClick={() => setOpen(false)}
                    className={({ isActive }) =>
                      `group flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all
                       ${isActive
                          ? 'bg-sheikah-teal/15 text-ink-primary'
                          : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/60'
                       }`
                    }
                  >
                    <BookOpen size={20} className="text-sheikah-teal-deep shrink-0" />
                    <span className="min-w-0">
                      <span className="block font-display text-base tracking-wide leading-tight">
                        Content Catalog
                      </span>
                      <span className="block font-script text-ink-whisper text-caption leading-tight">
                        items, pets, challenges
                      </span>
                    </span>
                  </NavLink>
                </>
              )}
              <NavLink
                to="/settings"
                role="menuitem"
                tabIndex={-1}
                onClick={() => setOpen(false)}
                className={({ isActive }) =>
                  `group flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all
                   ${isActive
                      ? 'bg-sheikah-teal/15 text-ink-primary'
                      : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/60'
                   }`
                }
              >
                <Settings size={20} className="text-sheikah-teal-deep shrink-0" />
                <span className="min-w-0">
                  <span className="block font-display text-base tracking-wide leading-tight">
                    Settings
                  </span>
                  <span className="block font-script text-ink-whisper text-caption leading-tight">
                    appearance and account
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
