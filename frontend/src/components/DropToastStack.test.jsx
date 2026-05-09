import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import DropToastStack from './DropToastStack.jsx';
import { server } from '../test/server.js';

// Stub AnimatePresence so exit animations don't keep the DOM node alive after
// state removes it. The real AnimatePresence schedules an exit animation
// that finishes asynchronously — in tests we want synchronous removal.
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return {
    ...actual,
    AnimatePresence: ({ children }) => children,
  };
});

// Mutable reference so server.use() handlers can pick up new drops on each
// poll without re-registering handlers.
const pollState = { drops: [] };

beforeEach(() => {
  pollState.drops = [];
  server.use(
    http.get('*/api/drops/recent/', () => HttpResponse.json(pollState.drops)),
  );
});

afterEach(() => {
  vi.useRealTimers();
});

describe('DropToastStack', () => {
  it('renders new drops as toasts after the initial seed poll', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<DropToastStack />);
    // Seed poll — toasts stays empty.
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    expect(screen.queryByText(/you got/i)).toBeNull();
    pollState.drops = [
      {
        id: 1,
        item_name: 'Gold Coin',
        item_icon: '🪙',
        item_sprite_key: 'coin',
        item_rarity: 'common',
        was_salvaged: false,
      },
    ];
    await act(async () => { await vi.advanceTimersByTimeAsync(25000); });
    await waitFor(() => expect(screen.getByText(/gold coin/i)).toBeInTheDocument());
  });

  it('shows Salvaged when was_salvaged=true', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<DropToastStack />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    pollState.drops = [{
      id: 2,
      item_name: 'Epic Helm',
      item_icon: '🪖',
      item_sprite_key: 'helm',
      item_rarity: 'epic',
      was_salvaged: true,
    }];
    await act(async () => { await vi.advanceTimersByTimeAsync(25000); });
    await waitFor(() =>
      expect(screen.getByText((content) => /salvaged/i.test(content))).toBeInTheDocument(),
    );
  });

  it('dismisses a toast when the X button is clicked', async () => {
    // Install fake timers BEFORE mount so the component's setInterval is
    // scheduled with fake timers.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<DropToastStack />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    pollState.drops = [{
      id: 3,
      item_name: 'Bone',
      item_icon: '🦴',
      item_sprite_key: 'bone',
      item_rarity: 'common',
      was_salvaged: false,
    }];
    await act(async () => { await vi.advanceTimersByTimeAsync(25000); });
    await waitFor(() => expect(screen.getByText(/bone/i)).toBeInTheDocument());
    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(screen.queryByText(/bone/i)).toBeNull());
  });

  it('auto-dismisses common toasts after 6 seconds', async () => {
    // Auto-dismiss only applies to the slide-in toast strip
    // (common/uncommon). Rare+ drops escalate to the RareDropReveal
    // modal which the user dismisses manually — see the burst test
    // below for the split.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<DropToastStack />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    pollState.drops = [{
      id: 4,
      item_name: 'RuneDrop',
      item_icon: 'R',
      item_sprite_key: 'rune',
      item_rarity: 'common',
      was_salvaged: false,
    }];
    await act(async () => { await vi.advanceTimersByTimeAsync(25000); });
    await waitFor(() => expect(screen.queryByText(/runedrop/i)).toBeInTheDocument());
    await act(async () => { await vi.advanceTimersByTimeAsync(6100); });
    await waitFor(() => expect(screen.queryByText(/runedrop/i)).toBeNull());
  });

  // 2026-04-23 review (R3): single quest completions like Master's Path can
  // fire a badge + an item drop + a frame + a title in the same poll window.
  // 2026-05 review: rare/epic/legendary drops now route to RareDropReveal
  // (one-at-a-time queue) while common/uncommon stay in the toast strip.
  // Verify both streams populate without dropping frames.
  it('routes rare drops to the reveal queue and queues commons in the strip', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<DropToastStack />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });

    pollState.drops = [
      { id: 10, item_name: 'Capstone Frame', item_icon: '🖼️', item_sprite_key: 'frame', item_rarity: 'epic', was_salvaged: false },
      { id: 11, item_name: 'Master Crafter Title', item_icon: '⚒️', item_sprite_key: '', item_rarity: 'legendary', was_salvaged: false },
      { id: 12, item_name: 'Quest Scroll', item_icon: '📜', item_sprite_key: 'scroll', item_rarity: 'rare', was_salvaged: false },
      { id: 13, item_name: 'Coin Pouch', item_icon: '👛', item_sprite_key: 'pouch', item_rarity: 'common', was_salvaged: false },
      { id: 14, item_name: 'Bone Shard', item_icon: '🦴', item_sprite_key: 'bone', item_rarity: 'uncommon', was_salvaged: false },
    ];
    await act(async () => { await vi.advanceTimersByTimeAsync(25000); });

    // The reveal queue surfaces only the topmost rare item at a time —
    // the 4-item burst means 3 rare items wait off-screen, but the
    // first one MUST render and have role="alertdialog".
    await waitFor(() =>
      expect(screen.getByRole('alertdialog')).toBeInTheDocument(),
    );
    // Common + uncommon land in the strip together.
    expect(screen.getByText(/coin pouch/i)).toBeInTheDocument();
    expect(screen.getByText(/bone shard/i)).toBeInTheDocument();
  });
});
