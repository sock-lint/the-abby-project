import { Outlet } from 'react-router-dom';
import { ChapterSidebar, ChapterBottomBar } from './ChapterNav';
import ClockFab from './ClockFab';
import NotificationBell from '../NotificationBell';
import AvatarMenu from '../AvatarMenu';
import DropToastStack from '../DropToastStack';
import PageTurnTransition from '../journal/PageTurnTransition';
import { useAuth } from '../../hooks/useApi';

/**
 * JournalShell — the Hyrule Field Notes outer layout.
 *
 * Structure:
 *   ┌──────────────┬────────────────────────────────┐
 *   │              │  Notification bell (top-right) │
 *   │  Chapter     │                                │
 *   │  Sidebar     │   <Outlet />                   │
 *   │  (desktop)   │   wrapped in PageTurnTransition│
 *   │              │                                │
 *   └──────────────┴────────────────────────────────┘
 *   [Mobile: bottom ChapterBottomBar + ClockFab FAB anchored bottom-right]
 */
export default function JournalShell() {
  const { user, logout } = useAuth();

  return (
    <div className="flex min-h-screen relative">
      <DropToastStack />
      <ChapterSidebar user={user} onLogout={logout} />

      <main className="flex-1 ml-0 md:ml-60 pb-28 md:pb-8 min-w-0">
        {/* Header — notification bell. On mobile we show a compact user chip. */}
        <header className="flex items-center justify-between px-4 md:px-6 pt-3 md:pt-4 gap-3">
          <div className="md:hidden min-w-0">
            <AvatarMenu user={user} compact />
          </div>
          <div className="md:ml-auto">
            <NotificationBell />
          </div>
        </header>

        <div className="px-4 md:px-6 pt-3 md:pt-6">
          <PageTurnTransition>
            <Outlet />
          </PageTurnTransition>
        </div>
      </main>

      <ChapterBottomBar />
      <ClockFab />
    </div>
  );
}
