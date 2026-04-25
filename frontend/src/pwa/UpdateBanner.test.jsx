import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import UpdateBanner from './UpdateBanner';
import { PwaStatusContext } from './PwaStatusProvider';

function renderWithStatus(value) {
  return render(
    <PwaStatusContext.Provider value={value}>
      <UpdateBanner />
    </PwaStatusContext.Provider>,
  );
}

describe('UpdateBanner', () => {
  it('renders nothing when updateReady is false', () => {
    const { container } = renderWithStatus({
      updateReady: false,
      offlineReady: false,
      applyUpdate: vi.fn(),
      dismissOfflineReady: vi.fn(),
    });
    expect(container).toBeEmptyDOMElement();
  });

  it('renders a status banner with Reload button when updateReady is true', () => {
    renderWithStatus({
      updateReady: true,
      offlineReady: false,
      applyUpdate: vi.fn(),
      dismissOfflineReady: vi.fn(),
    });
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/new version/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument();
  });

  it('clicking Reload calls applyUpdate from context', async () => {
    const applyUpdate = vi.fn();
    const user = userEvent.setup();
    renderWithStatus({
      updateReady: true,
      offlineReady: false,
      applyUpdate,
      dismissOfflineReady: vi.fn(),
    });
    await user.click(screen.getByRole('button', { name: /reload/i }));
    expect(applyUpdate).toHaveBeenCalledTimes(1);
  });
});
