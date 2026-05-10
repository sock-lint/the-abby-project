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
      <DropToastStack />
      <SavingsToastStack />
      <ApprovalToastStack />
      <QuestProgressToastStack />
      <CompanionGrowthToastStack />
      <ExpeditionToastStack />
      <FirstEncounterSheet />
      <ChapterSidebar user={user} onLogout={logout} />

      <main className="flex-1 ml-0 md:ml-60 pb-28 md:pb-8 min-w-0">
        <div className="sticky top-0 z-30 bg-ink-page backdrop-blur-[2px]">
          <header className="flex items-center px-4 md:px-6 pt-3 md:pt-4 pb-3 md:pb-4 gap-3">
            <div className="md:hidden min-w-0 shrink-0">
              <AvatarMenu user={user} compact />
            </div>
            <div className="flex-1 min-w-0 flex justify-end md:justify-center">
              <HeaderStatusPips user={user} />
            </div>
            <div className="shrink-0">
              <NotificationBell />
            </div>
          </header>

          <HeaderProgressBand />
        </div>

        <div className="px-4 md:px-6 pt-3 md:pt-6">
          <PageTurnTransition>
            <Outlet />
          </PageTurnTransition>
        </div>
      </main>

      <ChapterBottomBar />
      <QuickActionsFab />
    </div>
  );
}
