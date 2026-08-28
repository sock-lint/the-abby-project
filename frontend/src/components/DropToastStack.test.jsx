import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import DropToastStack from './DropToastStack.jsx';
import MockPulse from '../test/pulse.jsx';
import { emptyPulse } from '../test/pulseFixtures.js';

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

afterEach(() => {
  vi.useRealTimers();
});

const drop = (over = {}) => ({
  id: 1,
  item_name: 'Gold Coin',
  item_icon: '🪙',
  item_sprite_key: 'coin',
  item_rarity: 'common',
  was_salvaged: false,
  ...over,
});

/**
 * Render the stack under a heartbeat, then "beat" with new drops. The first
 * beat seeds the seen-set (a page load must not replay the last ten drops);
 * the second is what can toast.
 */
function renderWithBeats(drops) {
  const view = render(
    <MockPulse pulse={emptyPulse()}>
      <DropToastStack />
    </MockPulse>,
  );
  const beat = (next) => view.rerender(
    <MockPulse pulse={emptyPulse({ recent_drops: next })}>
      <DropToastStack />
    </MockPulse>,
  );
  if (drops) beat(drops);
  return { ...view, beat };
}

describe('DropToastStack', () => {
  it('seeds silently on the first beat', () => {
    render(
      <MockPulse pulse={emptyPulse({ recent_drops: [drop()] })}>
        <DropToastStack />
      </MockPulse>,
    );
    expect(screen.queryByText(/you got/i)).toBeNull();
  });

  it('renders drops that arrive after the seed beat', async () => {
    renderWithBeats([drop()]);
    await waitFor(() => expect(screen.getByText(/gold coin/i)).toBeInTheDocument());
  });

  it('shows Salvaged when was_salvaged=true', async () => {
    renderWithBeats([drop({ id: 2, item_name: 'Epic Helm', was_salvaged: true })]);
    await waitFor(() =>
      expect(screen.getByText((content) => /salvaged/i.test(content))).toBeInTheDocument(),
    );
  });

  it('dismisses a toast when the X button is clicked', async () => {
    renderWithBeats([drop({ id: 3, item_name: 'Bone' })]);
    await waitFor(() => expect(screen.getByText(/bone/i)).toBeInTheDocument());
    const buttons = screen.getAllByRole('button');
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(screen.queryByText(/bone/i)).toBeNull());
  });

  it('auto-dismisses common toasts after 6 seconds', async () => {
    // Auto-dismiss only applies to the slide-in toast strip
    // (common/uncommon). Rare+ drops escalate to the RareDropReveal modal
    // which the user dismisses manually — see the burst test below.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderWithBeats([drop({ id: 4, item_name: 'RuneDrop' })]);
    await waitFor(() => expect(screen.queryByText(/runedrop/i)).toBeInTheDocument());
    await act(async () => { await vi.advanceTimersByTimeAsync(6100); });
    await waitFor(() => expect(screen.queryByText(/runedrop/i)).toBeNull());
  });

  // A single quest completion can fire a badge + an item drop + a frame + a
  // title in the same beat. Rare/epic/legendary route to RareDropReveal
  // (one-at-a-time queue) while common/uncommon stay in the strip — verify
  // both streams populate without dropping frames.
  it('routes rare drops to the reveal queue and queues commons in the strip', async () => {
    renderWithBeats([
      drop({ id: 10, item_name: 'Capstone Frame', item_rarity: 'epic' }),
      drop({ id: 11, item_name: 'Master Crafter Title', item_rarity: 'legendary' }),
      drop({ id: 12, item_name: 'Quest Scroll', item_rarity: 'rare' }),
      drop({ id: 13, item_name: 'Coin Pouch', item_rarity: 'common' }),
      drop({ id: 14, item_name: 'Bone Shard', item_rarity: 'uncommon' }),
    ]);

    // The reveal queue surfaces only the topmost rare item at a time — the
    // burst means the rest wait off-screen, but the first MUST render.
    await waitFor(() => expect(screen.getByRole('alertdialog')).toBeInTheDocument());
    expect(screen.getByText(/coin pouch/i)).toBeInTheDocument();
    expect(screen.getByText(/bone shard/i)).toBeInTheDocument();
  });

  // A drop can land on the heartbeat while a kid is halfway through a form
  // sheet. The full-screen reveal must wait its turn rather than stacking a
  // second portal over the form and stealing its focus.
  it('holds the rare reveal back until an open dialog closes', async () => {
    const openSheet = document.createElement('div');
    openSheet.setAttribute('role', 'dialog');
    document.body.appendChild(openSheet);

    const { beat } = renderWithBeats();
    beat([drop({ id: 20, item_name: 'Sunset Cloak', item_rarity: 'epic' })]);

    // Give the gate a beat to settle — it must still be holding.
    await act(async () => { await new Promise((r) => setTimeout(r, 30)); });
    expect(screen.queryByText(/sunset cloak/i)).toBeNull();

    await act(async () => { openSheet.remove(); });
    await waitFor(() => expect(screen.getByRole('alertdialog')).toBeInTheDocument());
    expect(screen.getByText(/sunset cloak/i)).toBeInTheDocument();
  });
});
