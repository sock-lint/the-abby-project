import { Outlet } from 'react-router-dom';
import { ChapterSidebar, ChapterBottomBar } from './ChapterNav';
import QuickActionsFab from './QuickActionsFab';
import NotificationBell from '../NotificationBell';
import AvatarMenu from '../AvatarMenu';
import DropToastStack from '../DropToastStack';
import FirstEncounterSheet from '../lorebook/FirstEncounterSheet';
import SavingsToastStack from '../SavingsToastStack';
import ApprovalToastStack from '../ApprovalToastStack';
import QuestProgressToastStack from '../QuestProgressToastStack';
import CompanionGrowthToastStack from '../CompanionGrowthToastStack';
import ExpeditionToastStack from '../ExpeditionToastStack';
import PageTurnTransition from '../journal/PageTurnTransition';
import HeaderStatusPips from './HeaderStatusPips';
import HeaderProgressBand from './HeaderProgressBand';
import { useAuth } from '../../hooks/useApi';

/**
 * JournalShell — the Hyrule Field Notes outer layout.
 *
 *   ┌──────────────┬────────────────────────────────────────┐
 *   │              │  [avatar]  [status pips]   [🔔 bell]   │
 *   │  Chapter     │  ── HeaderProgressBand (quest) ──────  │
 *   │  Sidebar     │                                        │
 *   │  (desktop)   │   <Outlet />                           │
 *   └──────────────┴────────────────────────────────────────┘
 *   [Mobile: bottom ChapterBottomBar + QuickActionsFab bottom-right]
 */
export default function JournalShell() {
  const { user, logout } = useAuth();

  return (
    <div className="flex min-h-screen relative">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-sheikah-teal-deep focus:text-ink-page focus:rounded-lg focus:font-display focus:text-sm"
      >
        Skip to content
      </a>
      <div className="fixed top-4 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none" aria-live="polite" aria-atomic="false">
        <DropToastStack inline />
        <SavingsToastStack inline />
        <CompanionGrowthToastStack inline />
        <ExpeditionToastStack inline />
        <ApprovalToastStack inline />
        <QuestProgressToastStack inline />
      </div>
      <FirstEncounterSheet />
      <ChapterSidebar user={user} onLogout={logout} />

      <main id="main-content" className="flex-1 ml-0 lg:ml-60 pb-28 lg:pb-8 min-w-0">
        <div className="sticky top-0 z-30 bg-ink-page backdrop-blur-[2px]">
          <header className="flex items-center px-4 lg:px-6 pt-3 lg:pt-4 pb-3 lg:pb-4 gap-3">
            <div className="lg:hidden min-w-0 shrink-0">
              <AvatarMenu user={user} compact />
            </div>
            <div className="flex-1 min-w-0 flex justify-end lg:justify-center">
              <HeaderStatusPips user={user} />
            </div>
            <div className="shrink-0">
              <NotificationBell />
            </div>
          </header>

          <HeaderProgressBand />
        </div>

        <div className="px-4 lg:px-6 pt-3 lg:pt-6">
          <PageTurnTransition>
            <Outlet />
          </PageTurnTransition>
        </div>
      </main>

      <ChapterBottomBar user={user} />
      <QuickActionsFab />
    </div>
  );
}
