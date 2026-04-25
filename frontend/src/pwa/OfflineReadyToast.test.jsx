import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import OfflineReadyToast from './OfflineReadyToast';
import { PwaStatusContext } from './PwaStatusProvider';

function renderWithStatus(value) {
  return render(
    <PwaStatusContext.Provider value={value}>
      <OfflineReadyToast />
    </PwaStatusContext.Provider>,
  );
}

// AnimatePresence stubbed so exit animations don't block synchronous unmount.
vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('OfflineReadyToast', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders nothing observable when offlineReady is false', () => {
    renderWithStatus({
      updateReady: false,
      offlineReady: false,
      applyUpdate: vi.fn(),
      dismissOfflineReady: vi.fn(),
    });
    // Component always renders a positioning wrapper, but nothing with
    // role=status should be present when offlineReady is false.
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('renders the toast when offlineReady is true', () => {
    renderWithStatus({
      updateReady: false,
      offlineReady: true,
      applyUpdate: vi.fn(),
      dismissOfflineReady: vi.fn(),
    });
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/ready to work offline/i)).toBeInTheDocument();
  });

  it('auto-dismisses after 4 seconds', () => {
    const dismissOfflineReady = vi.fn();
    renderWithStatus({
      updateReady: false,
      offlineReady: true,
      applyUpdate: vi.fn(),
      dismissOfflineReady,
    });
    expect(dismissOfflineReady).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    expect(dismissOfflineReady).toHaveBeenCalledTimes(1);
  });

  it('clears the timer if unmounted before 4s', () => {
    const dismissOfflineReady = vi.fn();
    const { unmount } = renderWithStatus({
      updateReady: false,
      offlineReady: true,
      applyUpdate: vi.fn(),
      dismissOfflineReady,
    });
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    unmount();
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(dismissOfflineReady).not.toHaveBeenCalled();
  });
});
