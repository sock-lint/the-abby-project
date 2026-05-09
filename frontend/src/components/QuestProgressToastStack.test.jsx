import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../hooks/useApi.js';
import QuestProgressToastStack from './QuestProgressToastStack.jsx';
import { server } from '../test/server.js';
import { buildUser } from '../test/factories.js';

// Stub AnimatePresence so exit animations don't keep the toast alive after
// we expect synchronous removal.
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return {
    ...actual,
    AnimatePresence: ({ children }) => children,
  };
});

// Mutable reference so server.use() handlers can change response across polls.
const pollState = { quest: null };

function renderStack(user = buildUser()) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    http.get('*/api/quests/active/', () => HttpResponse.json(pollState.quest)),
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <QuestProgressToastStack />
      </AuthProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  pollState.quest = null;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('QuestProgressToastStack', () => {
  it('renders nothing when there is no active quest', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderStack();
    await act(async () => { await vi.advanceTimersByTimeAsync(100); });
    // No quest → no toasts at all.
    expect(screen.queryByText(/toward/i)).toBeNull();
  });

  it('emits a toast when current_progress increases between polls', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    pollState.quest = {
      id: 7,
      definition: { name: 'Dragon Slayer' },
      current_progress: 30,
      progress_percent: 60,
    };
    renderStack();
    // Seed poll establishes baseline at 30 — no toast yet.
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    expect(screen.queryByText(/toward/i)).toBeNull();

    // Bump progress; second poll should emit "+10 toward Dragon Slayer 62%".
    pollState.quest = {
      id: 7,
      definition: { name: 'Dragon Slayer' },
      current_progress: 40,
      progress_percent: 62,
    };
    await act(async () => { await vi.advanceTimersByTimeAsync(25_000); });
    await waitFor(() =>
      expect(screen.getByText(/\+10 toward dragon slayer/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/62% complete/i)).toBeInTheDocument();
  });

  it('auto-dismisses each toast after 4 seconds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    pollState.quest = {
      id: 7,
      definition: { name: 'Focus Master' },
      current_progress: 5,
      progress_percent: 10,
    };
    renderStack();
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    pollState.quest = {
      id: 7,
      definition: { name: 'Focus Master' },
      current_progress: 12,
      progress_percent: 24,
    };
    await act(async () => { await vi.advanceTimersByTimeAsync(25_000); });
    await waitFor(() =>
      expect(screen.getByText(/\+7 toward focus master/i)).toBeInTheDocument(),
    );
    // Wait 4s + a few ticks past the AUTO_DISMISS_MS window.
    await act(async () => { await vi.advanceTimersByTimeAsync(4_500); });
    await waitFor(() =>
      expect(screen.queryByText(/\+7 toward focus master/i)).toBeNull(),
    );
  });

  it('does not toast when progress decreases (idle-day rage decay shouldn\'t look like a win)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    pollState.quest = {
      id: 7,
      definition: { name: 'Backslide Boss' },
      current_progress: 50,
      progress_percent: 50,
    };
    renderStack();
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    // Decrease progress (e.g., rage-shield bumped away from completion).
    pollState.quest = {
      id: 7,
      definition: { name: 'Backslide Boss' },
      current_progress: 45,
      progress_percent: 45,
    };
    await act(async () => { await vi.advanceTimersByTimeAsync(25_000); });
    expect(screen.queryByText(/toward backslide boss/i)).toBeNull();
  });

  it('skips polling for parent role (parents have no personal active quest)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    pollState.quest = {
      id: 99,
      definition: { name: 'Parents Don\'t See This' },
      current_progress: 1,
      progress_percent: 1,
    };
    renderStack(buildUser({ role: 'parent' }));
    await act(async () => { await vi.advanceTimersByTimeAsync(50); });
    pollState.quest = {
      id: 99,
      definition: { name: 'Parents Don\'t See This' },
      current_progress: 50,
      progress_percent: 50,
    };
    await act(async () => { await vi.advanceTimersByTimeAsync(25_000); });
    expect(screen.queryByText(/toward/i)).toBeNull();
  });
});
