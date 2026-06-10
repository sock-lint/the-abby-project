import { describe, expect, it } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import OfflineBanner from './OfflineBanner.jsx';

function setOnLine(value) {
  Object.defineProperty(navigator, 'onLine', {
    value,
    configurable: true,
  });
}

describe('OfflineBanner', () => {
  it('renders nothing while online', () => {
    setOnLine(true);
    const { container } = render(<OfflineBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it('appears on the offline event and clears on online', () => {
    setOnLine(true);
    render(<OfflineBanner />);

    act(() => {
      window.dispatchEvent(new Event('offline'));
    });
    expect(screen.getByRole('status')).toHaveTextContent(/you're offline/i);

    act(() => {
      window.dispatchEvent(new Event('online'));
    });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('starts visible when the page loads already offline', () => {
    setOnLine(false);
    render(<OfflineBanner />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
