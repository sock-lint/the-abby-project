import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { renderWithProviders } from '../test/render';
import QuestProgressToastStack from './QuestProgressToastStack.jsx';
import { server } from '../test/server.js';
import { buildUser, buildParent } from '../test/factories.js';
import { emptyPulse } from '../test/pulseFixtures.js';

// Stub AnimatePresence so exit animations don't keep the toast alive after
// we expect synchronous removal.
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return {
    ...actual,
    AnimatePresence: ({ children }) => children,
  };
});

const quest = (over = {}) => ({
  id: 7,
  definition: { name: 'Dragon Slayer' },
  current_progress: 30,
  progress_percent: 60,
  ...over,
});

function renderStack(user = buildUser(), pulse = emptyPulse()) {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(user)));
  return renderWithProviders(<QuestProgressToastStack />, { pulse });
}

afterEach(() => {
  vi.useRealTimers();
});

describe('QuestProgressToastStack', () => {
  it('renders nothing when there is no active quest', async () => {
    renderStack();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/toward/i)).toBeNull();
  });

  it('emits a toast when current_progress increases between beats', async () => {
    // First beat with a quest establishes the baseline silently — otherwise
    // a page load would toast the quest's whole existing progress.
    const { beat } = renderStack(buildUser(), emptyPulse({ active_quest: quest() }));
    await waitFor(() => expect(screen.queryByText(/toward/i)).toBeNull());

    beat(emptyPulse({ active_quest: quest({ current_progress: 40, progress_percent: 80 }) }));

    await waitFor(() =>
      expect(screen.getByText(/dragon slayer/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/\+10/)).toBeInTheDocument();
    expect(screen.getByText(/80%/)).toBeInTheDocument();
  });

  it('auto-dismisses each toast after 4 seconds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { beat } = renderStack(buildUser(), emptyPulse({ active_quest: quest() }));
    await waitFor(() => expect(screen.queryByText(/toward/i)).toBeNull());

    beat(emptyPulse({ active_quest: quest({ current_progress: 40, progress_percent: 80 }) }));
    await waitFor(() => expect(screen.getByText(/dragon slayer/i)).toBeInTheDocument());

    await act(async () => { await vi.advanceTimersByTimeAsync(4_500); });
    await waitFor(() => expect(screen.queryByText(/dragon slayer/i)).toBeNull());
  });

  it("does not toast when progress decreases (idle-day rage decay shouldn't look like a win)", async () => {
    const { beat } = renderStack(buildUser(), emptyPulse({ active_quest: quest() }));
    await waitFor(() => expect(screen.queryByText(/toward/i)).toBeNull());

    beat(emptyPulse({ active_quest: quest({ current_progress: 20, progress_percent: 40 }) }));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/dragon slayer/i)).toBeNull();
  });

  it('stays silent for parent role (parents have no personal active quest)', async () => {
    const { beat } = renderStack(buildParent(), emptyPulse({ active_quest: quest() }));
    beat(emptyPulse({ active_quest: quest({ current_progress: 40, progress_percent: 80 }) }));
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/dragon slayer/i)).toBeNull();
  });
});
