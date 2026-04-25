import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock the virtual module BEFORE importing the provider. The mock exposes
// captured callbacks and the updateSW function so tests can simulate SW
// lifecycle events.
const mockState = {
  registerSW: null,
  updateSW: vi.fn(),
};

vi.mock('virtual:pwa-register', () => ({
  registerSW: vi.fn((opts) => {
    mockState.registerSW = opts;
    return mockState.updateSW;
  }),
}));

// Import the provider AFTER the mock is set up.
import { PwaStatusProvider, usePwaStatus } from './PwaStatusProvider';

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

describe('PwaStatusProvider', () => {
  beforeEach(() => {
    mockState.registerSW = null;
    mockState.updateSW.mockReset();
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

  it('applyUpdate calls updateSW(true)', async () => {
    const user = userEvent.setup();
    render(
      <PwaStatusProvider>
        <ApplyButton />
      </PwaStatusProvider>,
    );
    await waitFor(() => expect(mockState.registerSW).not.toBeNull());
    await user.click(screen.getByText('apply'));
    expect(mockState.updateSW).toHaveBeenCalledWith(true);
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
