import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render } from '@testing-library/react';
import Loader from './Loader.jsx';

describe('Loader', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders immediately with delayMs=0', () => {
    const { container } = render(<Loader delayMs={0} />);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('stays hidden before the delay elapses and appears after', () => {
    const { container } = render(<Loader delayMs={200} />);
    expect(container.firstChild).toBeNull();
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('cleans up the timeout on unmount', () => {
    const { unmount } = render(<Loader delayMs={500} />);
    unmount();
    // No pending timers should leak.
    expect(vi.getTimerCount()).toBe(0);
  });
});
