import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard, FolderKanban, ClipboardCheck, BookOpen, Zap, Package, Heart, Clock, FileText,
  DollarSign, Gift, Trophy, Camera, Settings, LogOut, MoreHorizontal,
  SlidersHorizontal,
} from 'lucide-react';
import NotificationBell from './NotificationBell';

const allNavItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/projects', icon: FolderKanban, label: 'Projects' },
  { to: '/chores', icon: ClipboardCheck, label: 'Chores' },
  { to: '/homework', icon: BookOpen, label: 'Homework' },
  { to: '/habits', icon: Zap, label: 'Habits' },
  { to: '/inventory', icon: Package, label: 'Inventory' },
  { to: '/stable', icon: Heart, label: 'Stable' },
  { to: '/clock', icon: Clock, label: 'Clock' },
  { to: '/timecards', icon: FileText, label: 'Timecards' },
  { to: '/payments', icon: DollarSign, label: 'Payments' },
  { to: '/rewards', icon: Gift, label: 'Rewards' },
  { to: '/achievements', icon: Trophy, label: 'Achievements' },
  { to: '/portfolio', icon: Camera, label: 'Portfolio' },
  { to: '/manage', icon: SlidersHorizontal, label: 'Manage', parentOnly: true },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

// Mobile bottom nav: 5 primary tabs + a "More" button that opens a sheet with the rest.
const mobilePrimary = ['/', '/projects', '/chores', '/clock', '/rewards'];

export default function Layout({ user, onLogout }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const navItems = allNavItems.filter((n) => !n.parentOnly || user?.role === 'parent');
  const primaryNavItems = navItems.filter((n) => mobilePrimary.includes(n.to));
  const overflowNavItems = navItems.filter((n) => !mobilePrimary.includes(n.to));

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 bg-forge-card border-r border-forge-border flex flex-col fixed h-full z-10
                         max-md:hidden">
        <div className="p-4 border-b border-forge-border">
          <h1 className="font-heading text-lg text-amber-highlight font-bold tracking-tight">
            The Abby Project
          </h1>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-amber-primary/15 text-amber-highlight'
                    : 'text-forge-text-dim hover:text-forge-text hover:bg-forge-muted/50'
                }`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-forge-border">
          <div className="flex items-center gap-2 px-2 mb-2">
            <div className="w-8 h-8 rounded-full bg-amber-primary/20 flex items-center justify-center text-amber-highlight text-sm font-bold">
              {(user?.display_name || user?.username || '?')[0].toUpperCase()}
            </div>
            <div className="text-sm truncate">
              <div className="text-forge-text">{user?.display_name || user?.username}</div>
              <div className="text-forge-text-dim text-xs capitalize">{user?.role}</div>
            </div>
          </div>
          <button
            onClick={onLogout}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-forge-text-dim hover:text-red-400 transition-colors w-full"
          >
            <LogOut size={16} /> Log out
          </button>
        </div>
      </aside>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-forge-card border-t border-forge-border flex justify-around z-10">
        {primaryNavItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex flex-col items-center justify-center gap-0.5 text-xs min-h-14 flex-1 ${
                isActive ? 'text-amber-highlight' : 'text-forge-text-dim'
              }`
            }
          >
            <Icon size={20} />
            {label}
          </NavLink>
        ))}
        <button
          type="button"
          onClick={() => setMoreOpen(true)}
          className={`flex flex-col items-center justify-center gap-0.5 text-xs min-h-14 flex-1 ${
            moreOpen ? 'text-amber-highlight' : 'text-forge-text-dim'
          }`}
        >
          <MoreHorizontal size={20} />
          More
        </button>
      </nav>

      {/* Mobile "More" bottom sheet */}
      <AnimatePresence>
        {moreOpen && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMoreOpen(false)}
              className="md:hidden fixed inset-0 bg-black/60 z-20"
            />
            <motion.div
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 300 }}
              className="md:hidden fixed bottom-0 left-0 right-0 bg-forge-card border-t border-forge-border rounded-t-2xl z-30 pb-[env(safe-area-inset-bottom)]"
            >
              <div className="flex justify-center pt-2">
                <div className="w-10 h-1 rounded-full bg-forge-muted" />
              </div>
              <div className="p-4">
                <div className="grid grid-cols-2 gap-2">
                  {overflowNavItems.map(({ to, icon: Icon, label }) => (
                    <NavLink
                      key={to}
                      to={to}
                      end={to === '/'}
                      onClick={() => setMoreOpen(false)}
                      className={({ isActive }) =>
                        `flex items-center gap-3 px-4 min-h-14 rounded-xl transition-colors ${
                          isActive
                            ? 'bg-amber-primary/15 text-amber-highlight'
                            : 'bg-forge-bg text-forge-text hover:bg-forge-muted/50'
                        }`
                      }
                    >
                      <Icon size={20} />
                      <span className="text-sm font-medium">{label}</span>
                    </NavLink>
                  ))}
                </div>
                <button
                  onClick={() => {
                    setMoreOpen(false);
                    onLogout();
                  }}
                  className="mt-3 w-full flex items-center justify-center gap-2 min-h-12 rounded-xl bg-forge-bg text-red-400 hover:bg-red-500/10 transition-colors text-sm font-medium"
                >
                  <LogOut size={18} /> Log out
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Main content */}
      <main className="flex-1 ml-0 md:ml-56 pb-20 md:pb-6">
        <div className="flex items-center justify-between p-3 md:hidden">
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              `flex items-center gap-2 min-w-0 rounded-lg px-2 py-1 -ml-2 transition-colors ${
                isActive ? 'bg-amber-primary/15' : 'hover:bg-forge-muted/50'
              }`
            }
          >
            <div className="w-9 h-9 shrink-0 rounded-full bg-amber-primary/20 flex items-center justify-center text-amber-highlight text-sm font-bold">
              {(user?.display_name || user?.username || '?')[0].toUpperCase()}
            </div>
            <div className="text-sm min-w-0">
              <div className="text-forge-text truncate leading-tight">
                {user?.display_name || user?.username}
              </div>
              <div className="text-forge-text-dim text-xs capitalize leading-tight">
                {user?.role}
              </div>
            </div>
          </NavLink>
          <NotificationBell />
        </div>
        <div className="hidden md:flex items-center justify-end px-6 pt-4">
          <NotificationBell />
        </div>
        <div className="px-4 md:px-6 pb-4 md:pb-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
