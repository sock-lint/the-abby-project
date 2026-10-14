import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock worker registration before importing the provider. The mock exposes
// captured callbacks and the updateSW function so tests can simulate SW
// lifecycle events.
const mockState = {
  registerSW: null,
  updateSW: vi.fn(),
};

vi.mock('./registerPromptWorker', () => ({
  registerPromptWorker: vi.fn((opts) => {
    mockState.registerSW = opts;
    return { update: mockState.updateSW, dispose: vi.fn() };
  }),
}));

// Import the provider AFTER the mock is set up.
import { PwaStatusProvider } from './PwaStatusProvider';
import { usePwaStatus } from './pwaStatus.context';
import { useFormState } from '../hooks/useFormState';
import BottomSheet from '../components/BottomSheet';

function StatusProbe() {
  const { updateReady, offlineReady } = usePwaStatus();
  return (
    <div>
      <span data-testid="update-ready">{String(updateReady)}</span>
      <span data-testid="offline-ready">{String(offlineReady)}</span>
    </div>
  );
}

function ApplyButton() {
  const { applyUpdate } = usePwaStatus();
  return <button onClick={applyUpdate}>apply</button>;
}

function DismissButton() {
  const { dismissOfflineReady } = usePwaStatus();
  return <button onClick={dismissOfflineReady}>dismiss</button>;
}

function DraftForm() {
  const { form, set } = useFormState({ note: '' });
  return <input aria-label="Unsaved note" value={form.note} onChange={(event) => set({ note: event.target.value })} />;
}

describe('PwaStatusProvider', () => {
  beforeEach(() => {
    mockState.registerSW = null;
    mockState.updateSW.mockReset();
  });

  it('preserves the waiting update and refuses activation while a form has unsaved work', async () => {
    render(<PwaStatusProvider><StatusProbe /><ApplyButton /><DraftForm /></PwaStatusProvider>);
    await waitFor(() => expect(mockState.registerSW).not.toBeNull());
    act(() => mockState.registerSW.onNeedRefresh());
    fireEvent.change(screen.getByLabelText('Unsaved note'), { target: { value: 'Keep this private thought' } });
    fireEvent.click(screen.getByText('apply'));
    expect(mockState.updateSW).not.toHaveBeenCalled();
    expect(screen.getByTestId('update-ready')).toHaveTextContent('true');
    expect(screen.getByLabelText('Unsaved note')).toHaveValue('Keep this private thought');
  });

  it('a blocked request does not invent an update before any waiting-worker proof', async () => {
    render(<PwaStatusProvider><StatusProbe /><ApplyButton /><DraftForm /></PwaStatusProvider>);
    fireEvent.change(screen.getByLabelText('Unsaved note'), { target: { value: 'Keep this thought' } });
    fireEvent.click(screen.getByText('apply'));
    expect(mockState.updateSW).not.toHaveBeenCalled();
    expect(screen.getByTestId('update-ready')).toHaveTextContent('false');
  });

  it('refuses activation during a busy sheet and releases its guard after unmount', async () => {
    const view = render(<PwaStatusProvider><StatusProbe /><ApplyButton /><BottomSheet title="Saving" disabled onClose={() => {}}>In progress</BottomSheet></PwaStatusProvider>);
    await waitFor(() => expect(mockState.registerSW).not.toBeNull());
    act(() => mockState.registerSW.onNeedRefresh());
    fireEvent.click(screen.getByText('apply'));
    expect(mockState.updateSW).not.toHaveBeenCalled();
    expect(screen.getByTestId('update-ready')).toHaveTextContent('true');
    view.rerender(<PwaStatusProvider><StatusProbe /><ApplyButton /></PwaStatusProvider>);
    fireEvent.click(screen.getByText('apply'));
    expect(mockState.updateSW).toHaveBeenCalledTimes(1);
  });

  it('starts with both flags false', () => {
    render(
      <PwaStatusProvider>
        <StatusProbe />
      </PwaStatusProvider>,
    );
    expect(screen.getByTestId('update-ready').textContent).toBe('false');
    expect(screen.getByTestId('offline-ready').textContent).toBe('false');
  });

  it('flips updateReady to true when onNeedRefresh fires', async () => {
    render(
      <PwaStatusProvider>
        <StatusProbe />
      </PwaStatusProvider>,
    );
    await waitFor(() => expect(mockState.registerSW).not.toBeNull());
    act(() => {
      mockState.registerSW.onNeedRefresh();
    });
    expect(screen.getByTestId('update-ready').textContent).toBe('true');
  });

  it('flips offlineReady to true when onOfflineReady fires', async () => {
    render(
      <PwaStatusProvider>
        <StatusProbe />
      </PwaStatusProvider>,
    );
    await waitFor(() => expect(mockState.registerSW).not.toBeNull());
    act(() => {
      mockState.registerSW.onOfflineReady();
    });
    expect(screen.getByTestId('offline-ready').textContent).toBe('true');
  });

  it('applyUpdate requests activation without delegating reload', async () => {
    const user = userEvent.setup();
    render(
      <PwaStatusProvider>
        <ApplyButton />
      </PwaStatusProvider>,
    );
    await waitFor(() => expect(mockState.registerSW).not.toBeNull());
    await user.click(screen.getByText('apply'));
    expect(mockState.updateSW).toHaveBeenCalledWith();
  });

  describe('applyUpdate reload safety net', () => {
    // Same pattern as client.test.js's 401 self-heal block: jsdom marks
    // Location.reload as non-configurable, so swap window.location with a
    // stub for this nested describe. Also stub navigator.serviceWorker so
    // the controllerchange listener is registered without throwing.
    let reloadSpy;
    let originalLocation;
    let swListeners;

    beforeEach(() => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      reloadSpy = vi.fn();
      originalLocation = window.location;
      Object.defineProperty(window, 'location', {
        configurable: true,
        writable: true,
        value: {
          href: originalLocation.href,
          origin: originalLocation.origin,
          protocol: originalLocation.protocol,
          host: originalLocation.host,
          hostname: originalLocation.hostname,
          port: originalLocation.port,
          pathname: originalLocation.pathname,
          search: originalLocation.search,
          hash: originalLocation.hash,
          reload: reloadSpy,
        },
      });
      swListeners = {};
      Object.defineProperty(navigator, 'serviceWorker', {
        configurable: true,
        value: {
          addEventListener: vi.fn((type, listener) => {
            swListeners[type] = listener;
          }),
          removeEventListener: vi.fn(),
          controller: null,
          ready: Promise.resolve({}),
          register: vi.fn(() => Promise.resolve({})),
        },
      });
    });

    afterEach(() => {
      vi.useRealTimers();
      Object.defineProperty(window, 'location', {
        configurable: true,
        writable: true,
        value: originalLocation,
      });
    });

    it('reloads when controllerchange fires after applyUpdate', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(
        <PwaStatusProvider>
          <ApplyButton />
        </PwaStatusProvider>,
      );
      await waitFor(() => expect(mockState.registerSW).not.toBeNull());
      await user.click(screen.getByText('apply'));
      expect(typeof swListeners.controllerchange).toBe('function');
      expect(reloadSpy).not.toHaveBeenCalled();
      act(() => {
        swListeners.controllerchange();
      });
      expect(reloadSpy).toHaveBeenCalledTimes(1);
    });

    it('defers controller and timeout reload when new work opens after activation starts', async () => {
      render(<PwaStatusProvider><StatusProbe /><ApplyButton /><DraftForm /></PwaStatusProvider>);
      await waitFor(() => expect(mockState.registerSW).not.toBeNull());
      act(() => mockState.registerSW.onNeedRefresh());
      fireEvent.click(screen.getByText('apply'));
      fireEvent.change(screen.getByLabelText('Unsaved note'), { target: { value: 'Written during update' } });
      act(() => swListeners.controllerchange());
      act(() => vi.advanceTimersByTime(1500));
      expect(reloadSpy).not.toHaveBeenCalled();
      expect(screen.getByTestId('update-ready')).toHaveTextContent('true');
      expect(screen.getByLabelText('Unsaved note')).toHaveValue('Written during update');
      fireEvent.change(screen.getByLabelText('Unsaved note'), { target: { value: '' } });
      fireEvent.click(screen.getByText('apply'));
      act(() => vi.advanceTimersByTime(1500));
      expect(reloadSpy).toHaveBeenCalledTimes(1);
      expect(mockState.updateSW).toHaveBeenCalledTimes(1);
    });

    it('cancels the timeout and listener when its session provider unmounts', async () => {
      const view = render(<PwaStatusProvider><ApplyButton /></PwaStatusProvider>);
      await waitFor(() => expect(mockState.registerSW).not.toBeNull());
      fireEvent.click(screen.getByText('apply'));
      const staleListener = swListeners.controllerchange;
      view.unmount();
      act(() => staleListener());
      act(() => vi.advanceTimersByTime(1500));
      expect(reloadSpy).not.toHaveBeenCalled();
    });

    it('reloads via the timeout fallback when controllerchange never fires', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(
        <PwaStatusProvider>
          <ApplyButton />
        </PwaStatusProvider>,
      );
      await waitFor(() => expect(mockState.registerSW).not.toBeNull());
      await user.click(screen.getByText('apply'));
      expect(reloadSpy).not.toHaveBeenCalled();
      act(() => {
        vi.advanceTimersByTime(1500);
      });
      expect(reloadSpy).toHaveBeenCalledTimes(1);
    });

    it('reloads exactly once when both controllerchange and the fallback fire', async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(
        <PwaStatusProvider>
          <ApplyButton />
        </PwaStatusProvider>,
      );
      await waitFor(() => expect(mockState.registerSW).not.toBeNull());
      await user.click(screen.getByText('apply'));
      act(() => {
        swListeners.controllerchange();
      });
      act(() => {
        vi.advanceTimersByTime(1500);
      });
      expect(reloadSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe('reload-attempt suppression', () => {
    const PWA_RELOAD_KEY = 'pwa:last-reload-attempt';

    it('applyUpdate flips updateReady back to false immediately', async () => {
      const user = userEvent.setup();
      render(
        <PwaStatusProvider>
          <StatusProbe />
          <ApplyButton />
        </PwaStatusProvider>,
      );
      await waitFor(() => expect(mockState.registerSW).not.toBeNull());
      act(() => {
        mockState.registerSW.onNeedRefresh();
      });
      expect(screen.getByTestId('update-ready').textContent).toBe('true');
      await user.click(screen.getByText('apply'));
      expect(screen.getByTestId('update-ready').textContent).toBe('false');
    });

    it('swallows onNeedRefresh that fires inside the suppression window', async () => {
      window.localStorage.setItem(PWA_RELOAD_KEY, String(Date.now()));
      render(
        <PwaStatusProvider>
          <StatusProbe />
        </PwaStatusProvider>,
      );
      await waitFor(() => expect(mockState.registerSW).not.toBeNull());
      act(() => {
        mockState.registerSW.onNeedRefresh();
      });
      expect(screen.getByTestId('update-ready').textContent).toBe('false');
      // The suppression key is one-shot — cleared after the swallow so a
      // second genuine onNeedRefresh later in the same session still surfaces.
      expect(window.localStorage.getItem(PWA_RELOAD_KEY)).toBeNull();
    });

    it('honors onNeedRefresh once the stored timestamp is older than the window', async () => {
      // 2 minutes ago — well past the 60s suppression window.
      window.localStorage.setItem(
        PWA_RELOAD_KEY,
        String(Date.now() - 2 * 60_000),
      );
      render(
        <PwaStatusProvider>
          <StatusProbe />
        </PwaStatusProvider>,
      );
      await waitFor(() => expect(mockState.registerSW).not.toBeNull());
      act(() => {
        mockState.registerSW.onNeedRefresh();
      });
      expect(screen.getByTestId('update-ready').textContent).toBe('true');
    });
  });

  it('dismissOfflineReady flips offlineReady back to false', async () => {
    const user = userEvent.setup();
    render(
      <PwaStatusProvider>
        <StatusProbe />
        <DismissButton />
      </PwaStatusProvider>,
    );
    await waitFor(() => expect(mockState.registerSW).not.toBeNull());
    act(() => {
      mockState.registerSW.onOfflineReady();
    });
    expect(screen.getByTestId('offline-ready').textContent).toBe('true');
    await user.click(screen.getByText('dismiss'));
    expect(screen.getByTestId('offline-ready').textContent).toBe('false');
  });

  it('usePwaStatus has safe defaults outside the provider', () => {
    // Don't crash when used in isolated tests that mount components without
    // the provider — just expose the no-op shape.
    render(<StatusProbe />);
    expect(screen.getByTestId('update-ready').textContent).toBe('false');
    expect(screen.getByTestId('offline-ready').textContent).toBe('false');
  });
});
