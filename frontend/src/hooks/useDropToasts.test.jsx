import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import MockPulse from '../test/pulse.jsx';
import { emptyPulse } from '../test/pulseFixtures.js';
import { useDropToasts } from './useDropToasts.js';

const makeDrop = (over = {}) => ({
  id: 1,
  item_name: 'Ember Potion',
  item_icon: 'flask',
  item_sprite_key: 'ember',
  item_rarity: 'common',
  was_salvaged: false,
  ...over,
});

/** Render the hook under a heartbeat, with a `beat` to deliver a new one. */
function renderWithPulse(initial = emptyPulse()) {
  let current = initial;
  const view = renderHook(() => useDropToasts(), {
    wrapper: ({ children }) => <MockPulse pulse={current}>{children}</MockPulse>,
  });
  return {
    ...view,
    beat: (pulse) => { current = pulse; view.rerender(); },
  };
}

describe('useDropToasts', () => {
  it('suppresses toasts on the first beat (seeds seen IDs)', async () => {
    const { result } = renderWithPulse(
      emptyPulse({ recent_drops: [makeDrop({ id: 1 }), makeDrop({ id: 2 })] }),
    );
    await waitFor(() => expect(result.current.toasts).toEqual([]));
  });

  it('emits a toast for a drop that appears after the seed beat', async () => {
    const { result, beat } = renderWithPulse();
    await waitFor(() => expect(result.current.toasts).toEqual([]));

    beat(emptyPulse({ recent_drops: [makeDrop({ id: 5, item_name: 'Gold Coin' })] }));

    await waitFor(() => expect(result.current.toasts).toHaveLength(1));
    expect(result.current.toasts[0]).toMatchObject({ id: 5, item_name: 'Gold Coin' });
  });

  it('never re-toasts a drop it has already seen', async () => {
    const { result, beat } = renderWithPulse();
    const drop = makeDrop({ id: 9 });
    beat(emptyPulse({ recent_drops: [drop] }));
    await waitFor(() => expect(result.current.toasts).toHaveLength(1));

    // The same drop stays in the payload on the next beat — it must not
    // stack a second toast.
    beat(emptyPulse({ recent_drops: [drop] }));
    await waitFor(() => expect(result.current.toasts).toHaveLength(1));
  });

  it('dismiss removes a toast by id', async () => {
    const { result, beat } = renderWithPulse();
    beat(emptyPulse({ recent_drops: [makeDrop({ id: 3 })] }));
    await waitFor(() => expect(result.current.toasts).toHaveLength(1));

    result.current.dismiss(3);
    await waitFor(() => expect(result.current.toasts).toHaveLength(0));
  });

  it('tolerates a malformed payload', async () => {
    const { result, beat } = renderWithPulse();
    beat(emptyPulse({ recent_drops: null }));
    await waitFor(() => expect(result.current.toasts).toEqual([]));
  });
});
