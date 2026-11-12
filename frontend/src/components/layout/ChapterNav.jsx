import { NavLink } from 'react-router-dom';
import { SlidersHorizontal, Settings, LogOut, History, BookOpen, Sparkles, UsersRound } from 'lucide-react';
import { TodayIcon, QuestsIcon, BestiaryIcon, TreasuryIcon, AtlasIcon, ChronicleIcon } from '../icons/JournalIcons';
import AvatarMenu from '../AvatarMenu';
import useParentPendingCounts from '../../hooks/useParentPendingCounts';
import { useSpaceForUser } from '../../hooks/useSpace';

/**
 * ChapterNav — renders the current workspace's navigation in two flavors:
 *   - desktop : soft navigation rail with icons + labels
 *   - mobile  : bottom tab bar, four Family or six personal destinations
 *
 * The Clock is NOT a chapter — it lives in ClockFab (floating action).
 * Manage / Activity / Content Catalog (parent-only) sit in the desktop
 * sidebar footer. Mobile reaches those utilities through AvatarMenu.
 * Parent permission is unchanged; My space has the same personal navigation
 * as a child account, while Family organizes household work and children.
 *
 * The /codex link reads "Content Catalog", matching the page heading: it
 * administers the RPG catalog, not the kid-facing Lorebook, and "Codex"
 * already names the Bestiary hub's species tab.
 */

const CHAPTERS = [
  { to: '/',           icon: TodayIcon,     label: 'Today',     shortLabel: 'Today' },
  { to: '/quests',     icon: QuestsIcon,    label: 'Tasks',    shortLabel: 'Tasks' },
  { to: '/bestiary',   icon: BestiaryIcon,  label: 'Pets',  shortLabel: 'Pets' },
  { to: '/treasury',   icon: TreasuryIcon,  label: 'Rewards',  shortLabel: 'Rewards' },
  { to: '/atlas',      icon: AtlasIcon,     label: 'Progress',     shortLabel: 'Progress' },
  { to: '/chronicle',  icon: ChronicleIcon, label: 'Memories', shortLabel: 'Memories' },
];

const FAMILY_CHAPTERS = [CHAPTERS[0], CHAPTERS[1],
  { to: '/family', icon: UsersRound, label: 'Children', shortLabel: 'Children' }, CHAPTERS[3]];

export function ChapterSidebar({ user, onLogout }) {
  const isParent = user?.role === 'parent';
  const { isFamilySpace } = useSpaceForUser(user);
  const chapters = isFamilySpace ? FAMILY_CHAPTERS : CHAPTERS;
  const { total: pendingCount, ready, incomplete } = useParentPendingCounts({ enabled: isParent });
  return (
    <aside
      className="w-60 shrink-0 fixed h-full z-30 max-lg:hidden flex flex-col
                 bg-ink-page-aged/90 border-r border-ink-page-shadow/60 font-body"
    >
      <div className="p-5">
        <div className="size-11 flex items-center justify-center rounded-2xl bg-sheikah-teal/15 text-sheikah-teal-deep mb-3" aria-hidden="true">
          <Sparkles size={24} />
        </div>
        <h1 className="font-body font-bold text-lg leading-snug text-ink-primary">
          The Abby Project
        </h1>
        <div className="font-body text-ink-secondary text-caption mt-1 truncate">
          {isFamilySpace ? `${user?.family?.name || 'Your family'} · Family` : user?.display_name || user?.username
            ? `${user.display_name || user.username}’s little world`
            : 'Your little world'}
        </div>
      </div>

      {/* Chapter list */}
      <nav aria-label="Main navigation" className="flex-1 overflow-y-auto px-3 pb-3 space-y-1.5">
        {chapters.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `group flex items-center gap-3 min-h-11 px-3 py-2.5 rounded-2xl border transition-colors relative
               ${isActive
                 ? 'bg-sheikah-teal/15 border-sheikah-teal/20 text-ink-primary'
                 : 'border-transparent text-ink-secondary hover:text-ink-primary hover:bg-ink-page/80'
               }`
            }
          >
            {({ isActive }) => (
              <>
                <span className="relative shrink-0">
                  <Icon
                    size={22}
                    className={isActive ? 'text-sheikah-teal-deep' : ''}
                  />
                  {to === '/' && isFamilySpace && (pendingCount > 0 || !ready || incomplete) && (
                    <span
                      className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-ember-deep text-ink-page text-micro font-body font-bold leading-none px-1"
                      aria-label={!ready ? 'Checking reviews' : incomplete ? 'Some review queues are unavailable' : `${pendingCount} items needing attention`}
                    >
                      {!ready ? '…' : incomplete ? '?' : pendingCount > 9 ? '9+' : pendingCount}
                    </span>
                  )}
                </span>
                <span className="font-body font-semibold text-body">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Utility + user footer */}
      <div className="p-3 border-t border-ink-page-shadow/60 bg-ink-page/40 space-y-1">
        {isParent && (
          <NavLink
            to="/activity"
            className={({ isActive }) =>
              `flex items-center gap-2 min-h-11 px-3 py-2 rounded-2xl text-body font-body font-semibold transition-colors ${
                isActive
                  ? 'bg-sheikah-teal/15 text-ink-primary [&>svg]:text-sheikah-teal-deep'
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
              `flex items-center gap-2 min-h-11 px-3 py-2 rounded-2xl text-body font-body font-semibold transition-colors ${
                isActive
                  ? 'bg-sheikah-teal/15 text-ink-primary [&>svg]:text-sheikah-teal-deep'
                  : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/60'
              }`
            }
          >
            <SlidersHorizontal size={16} />
            Manage
          </NavLink>
        )}
        {isParent && (
          <NavLink
            to="/codex"
            className={({ isActive }) =>
              `flex items-center gap-2 min-h-11 px-3 py-2 rounded-2xl text-body font-body font-semibold transition-colors ${
                isActive
                  ? 'bg-sheikah-teal/15 text-ink-primary [&>svg]:text-sheikah-teal-deep'
                  : 'text-ink-secondary hover:text-ink-primary hover:bg-ink-page/60'
              }`
            }
          >
            <BookOpen size={16} />
            Content Catalog
          </NavLink>
        )}
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex items-center gap-2 min-h-11 px-3 py-2 rounded-2xl text-body font-body font-semibold transition-colors ${
              isActive
                ? 'bg-sheikah-teal/15 text-ink-primary [&>svg]:text-sheikah-teal-deep'
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
          className="flex items-center gap-2 min-h-11 px-3 py-2 rounded-2xl font-body font-semibold text-body w-full text-ink-secondary hover:bg-ember/10 hover:text-ember-deep transition-colors"
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

export function ChapterBottomBar({ user }) {
  const isParent = user?.role === 'parent';
  const { isFamilySpace } = useSpaceForUser(user);
  const { total: pendingCount, ready, incomplete } = useParentPendingCounts({ enabled: isParent });

  // Family utilities remain in AvatarMenu; personal chapters belong in My space.
  const chapters = isFamilySpace ? FAMILY_CHAPTERS : CHAPTERS;

  return (
    <nav
      data-journal-bottom-nav="true"
      aria-label="Main navigation"
      className="lg:hidden fixed bottom-0 left-0 right-0 z-30 flex min-[360px]:gap-1 pt-2
                 bg-ink-page-aged/95 backdrop-blur-sm border-t border-ink-page-shadow/60
                 pb-[calc(0.5rem+env(safe-area-inset-bottom))]
                 pl-[max(0.5rem,env(safe-area-inset-left))] pr-[max(0.5rem,env(safe-area-inset-right))]"
    >
      {chapters.map(({ to, icon: Icon, shortLabel }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          aria-label={shortLabel}
          className={({ isActive }) =>
            `flex flex-col items-center justify-center gap-1 min-h-14 min-w-0 flex-1 rounded-2xl border transition-colors relative ${
              isActive ? 'bg-sheikah-teal/15 border-sheikah-teal/20 text-ink-primary' : 'border-transparent text-ink-secondary hover:bg-ink-page'
            }`
          }
        >
          {({ isActive }) => (
            <>
              <span className="relative">
                <Icon size={20} className={isActive ? 'text-sheikah-teal-deep' : ''} />
                {to === '/' && isFamilySpace && (pendingCount > 0 || !ready || incomplete) && (
                  <span
                    className="absolute -top-1 -right-2 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-ember-deep text-ink-page text-micro font-body font-bold leading-none px-1"
                    aria-label={!ready ? 'Checking reviews' : incomplete ? 'Some review queues are unavailable' : `${pendingCount} items needing attention`}
                  >
                    {!ready ? '…' : incomplete ? '?' : pendingCount > 9 ? '9+' : pendingCount}
                  </span>
                )}
              </span>
              {/* Labels always render — iPhones are 375-393px CSS wide, and
                  the old min-[400px] gate left five unlabeled fantasy icons
                  on exactly the phones this app lives on. */}
              <span className="max-w-full truncate font-body font-semibold text-micro min-[360px]:text-tiny leading-none">
                {shortLabel}
              </span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

const ChapterNav = { ChapterSidebar, ChapterBottomBar };
export default ChapterNav;
