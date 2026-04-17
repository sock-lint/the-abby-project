import { describe, expect, it, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import Loader from './Loader.jsx';

describe('Loader', () => {
  it('renders nothing before delayMs elapses', () => {
    vi.useFakeTimers();
    const { container } = render(<Loader delayMs={200} />);
    expect(container.firstChild).toBeNull();
    vi.useRealTimers();
  });

  it('renders the spinner after the delay', () => {
    vi.useFakeTimers();
    render(<Loader delayMs={50} />);
    act(() => { vi.advanceTimersByTime(60); });
    expect(screen.getByRole('status')).toBeInTheDocument();
    vi.useRealTimers();
  });

  it('renders immediately when delayMs is 0', () => {
    render(<Loader delayMs={0} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('exposes aria-busy and an accessible name to screen readers', () => {
    render(<Loader delayMs={0} />);
    const status = screen.getByRole('status');
    expect(status).toHaveAttribute('aria-busy', 'true');
    expect(status).toHaveAccessibleName(/loading/i);
  });

  it('cleans up the timeout on unmount', () => {
    vi.useFakeTimers();
    const { unmount } = render(<Loader delayMs={500} />);
    unmount();
    // No pending timers should leak.
    expect(vi.getTimerCount()).toBe(0);
    vi.useRealTimers();
  });
});
