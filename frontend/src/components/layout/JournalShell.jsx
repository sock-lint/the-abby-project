import { Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import { ChapterSidebar, ChapterBottomBar } from './ChapterNav';
import ParchmentSkeleton from '../ParchmentSkeleton';
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
  const { user, logout, offline } = useAuth();

  return (
    <div className="flex min-h-dvh relative">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-4 focus:py-2 focus:bg-sheikah-teal-deep focus:text-ink-page focus:rounded-lg focus:font-display focus:text-sm"
      >
        Skip to content
      </a>
      <div className="fixed top-[calc(env(safe-area-inset-top)+1rem)] right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none" aria-live="polite" aria-atomic="false">
        <DropToastStack inline />
        <SavingsToastStack inline />
        <CompanionGrowthToastStack inline />
        <ExpeditionToastStack inline />
        <ApprovalToastStack inline />
        <QuestProgressToastStack inline />
      </div>
      <FirstEncounterSheet />
      <ChapterSidebar user={user} onLogout={logout} />

      <main id="main-content" className="flex-1 ml-0 lg:ml-60 pb-20 lg:pb-8 min-w-0">
        {/* pt-[env(safe-area-inset-top)] keeps the header clear of the iOS
            status bar in the installed PWA (viewport-fit=cover draws the
            page under it); the parchment backdrop still extends beneath. */}
        <div className="sticky top-0 z-30 bg-ink-page backdrop-blur-[2px] pt-[env(safe-area-inset-top)]">
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

          {/* Offline banner — shown when AuthProvider hydrated the session
              from the cached /auth/me/ snapshot because the network was
              unreachable at boot. Lives inside the sticky band so it stays
              visible while scrolling a stale page. */}
          {offline && (
            <div
              role="status"
              className="bg-ink-page-aged border-y border-ink-page-shadow px-4 lg:px-6 py-1.5 text-center font-body text-caption text-ink-secondary"
            >
              Offline — showing your last journal
            </div>
          )}
        </div>

        <div className="px-4 lg:px-6 pt-3 lg:pt-6">
          {/* Suspense boundary for the lazy page chunks (App.jsx). Sitting
              inside <main> keeps the sticky header + nav mounted while a
              chunk downloads; the parchment skeleton fills the content well
              so the page structure reads as "loading", not "blank". */}
          <Suspense
            fallback={(
              <div className="space-y-3">
                <ParchmentSkeleton variant="hero" />
                <ParchmentSkeleton variant="list" />
              </div>
            )}
          >
            <PageTurnTransition>
              <Outlet />
            </PageTurnTransition>
          </Suspense>
        </div>
      </main>

      <ChapterBottomBar user={user} />
      <QuickActionsFab />
    </div>
  );
}
