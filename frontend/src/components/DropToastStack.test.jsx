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

  it('auto-dismisses after 6 seconds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<DropToastStack />);
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    pollState.drops = [{
      id: 4,
      item_name: 'RuneDrop',
      item_icon: 'R',
      item_sprite_key: 'rune',
      item_rarity: 'rare',
      was_salvaged: false,
    }];
    await act(async () => { await vi.advanceTimersByTimeAsync(25000); });
    await waitFor(() => expect(screen.queryByText(/runedrop/i)).toBeInTheDocument());
    await act(async () => { await vi.advanceTimersByTimeAsync(6100); });
    await waitFor(() => expect(screen.queryByText(/runedrop/i)).toBeNull());
  });
});
