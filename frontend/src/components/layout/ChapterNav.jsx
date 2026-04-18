import { NavLink } from 'react-router-dom';
import { SlidersHorizontal, Settings, LogOut, History } from 'lucide-react';
import {
  TodayIcon, QuestsIcon, BestiaryIcon, TreasuryIcon, AtlasIcon,
} from '../icons/JournalIcons';
import AvatarMenu from '../AvatarMenu';

/**
 * ChapterNav — renders the five-chapter nav in two flavors:
 *   - desktop : left-side parchment rail with chapter icons + labels
 *   - mobile  : bottom tab bar, five equal columns
 *
 * The Clock is NOT a chapter — it lives in ClockFab (floating action).
 * Manage (parent-only) and Settings sit in the desktop sidebar footer.
 * Mobile has no footer — Settings is reached via the header AvatarMenu; Manage
 * is desktop-only since parents rarely manage on mobile.
 */

const CHAPTERS = [
  { to: '/',           icon: TodayIcon,     label: 'Today',    shortLabel: 'Today' },
  { to: '/quests',     icon: QuestsIcon,    label: 'Quests',   shortLabel: 'Quests' },
  { to: '/bestiary',   icon: BestiaryIcon,  label: 'Bestiary', shortLabel: 'Bestiary' },
  { to: '/treasury',   icon: TreasuryIcon,  label: 'Treasury', shortLabel: 'Treasury' },
  { to: '/atlas',      icon: AtlasIcon,     label: 'Atlas',    shortLabel: 'Atlas' },
];

export function ChapterSidebar({ user, onLogout }) {
  const isParent = user?.role === 'parent';
  return (
    <aside
      className="w-60 shrink-0 fixed h-full z-10 max-md:hidden flex flex-col
                 bg-ink-page-aged/90 border-r border-ink-page-shadow
                 shadow-[2px_0_0_var(--color-ink-page-rune-glow)_inset]"
    >
      {/* Book spine header */}
      <div className="p-5 border-b border-ink-page-shadow relative">
        <div className="font-script text-ink-whisper text-xs uppercase tracking-[0.2em]">
          a codex of
        </div>
        <h1 className="font-display italic text-2xl leading-tight text-ink-primary">
          Hyrule Field Notes
        </h1>
        <div className="font-script text-sheikah-teal-deep text-sm mt-1">
          vol. I — {user?.display_name || user?.username || 'adventurer'}
        </div>
      </div>

      {/* Chapter list */}
      <nav className="flex-1 overflow-y-auto p-3 space-y-1">
        {CHAPTERS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `group flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all relative
               ${isActive
                 ? 'bg-sheikah-teal/15 text-ink-primary'
                 : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/60'
               }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span
                    className="absolute left-0 top-1 bottom-1 w-0.5 rounded-r-full bg-sheikah-teal-deep"
                    aria-hidden="true"
                  />
                )}
                <Icon
                  size={22}
                  className={isActive ? 'text-sheikah-teal-deep animate-rune-pulse' : ''}
                />
                <span className="font-display text-base tracking-wide">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Utility + user footer */}
      <div className="p-3 border-t border-ink-page-shadow bg-ink-page/40 space-y-1">
        {isParent && (
          <NavLink
            to="/activity"
            className={({ isActive }) =>
              `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-body transition-colors ${
                isActive
                  ? 'bg-sheikah-teal/10 text-ink-primary'
                  : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/60'
              }`
            }
          >
            <History size={16} />
            Activity
          </NavLink>
        )}
        {isParent && (
          <NavLink
            to="/manage"
            className={({ isActive }) =>
              `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-body transition-colors ${
                isActive
                  ? 'bg-sheikah-teal/10 text-ink-primary'
                  : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/60'
              }`
            }
          >
            <SlidersHorizontal size={16} />
            Manage
          </NavLink>
        )}
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-body transition-colors ${
              isActive
                ? 'bg-sheikah-teal/10 text-ink-primary'
                : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/60'
            }`
          }
        >
          <Settings size={16} />
          Settings
        </NavLink>
        <button
          onClick={onLogout}
          type="button"
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm w-full text-ink-whisper hover:text-ember-deep transition-colors"
        >
          <LogOut size={16} /> Sign off
        </button>
        <div className="pt-2 mt-2 border-t border-ink-page-shadow/60">
          <AvatarMenu user={user} align="top" />
        </div>
      </div>
    </aside>
  );
}

export function ChapterBottomBar() {
  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-10 flex justify-around
                 bg-ink-page-aged/95 backdrop-blur-sm border-t border-ink-page-shadow
                 pb-[env(safe-area-inset-bottom)]
                 shadow-[0_-2px_0_var(--color-ink-page-rune-glow)_inset]"
    >
      {CHAPTERS.map(({ to, icon: Icon, shortLabel }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            `flex flex-col items-center justify-center gap-0.5 min-h-16 flex-1 transition-colors relative ${
              isActive ? 'text-sheikah-teal-deep' : 'text-ink-secondary'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <Icon size={22} className={isActive ? 'animate-rune-pulse' : ''} />
              <span className="font-script text-tiny leading-none">{shortLabel}</span>
              {isActive && (
                <span
                  className="absolute top-0.5 h-0.5 w-10 rounded-full bg-sheikah-teal-deep"
                  aria-hidden="true"
                />
              )}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

const ChapterNav = { ChapterSidebar, ChapterBottomBar };
export default ChapterNav;
