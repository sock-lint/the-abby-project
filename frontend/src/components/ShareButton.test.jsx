import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ShareButton from './ShareButton.jsx';

function stubShare(impl = vi.fn().mockResolvedValue(undefined)) {
  Object.defineProperty(navigator, 'share', {
    value: impl,
    configurable: true,
    writable: true,
  });
  return impl;
}

afterEach(() => {
  delete navigator.share;
});

describe('ShareButton', () => {
  it('renders nothing when navigator.share is unavailable', () => {
    const { container } = render(<ShareButton title="t" text="x" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('calls navigator.share with a text-only payload by default', async () => {
    const share = stubShare();
    const user = userEvent.setup();
    render(<ShareButton title="Badge earned" text="I earned a badge!" />);

    await user.click(screen.getByRole('button', { name: /share/i }));

    expect(share).toHaveBeenCalledWith({
      title: 'Badge earned',
      text: 'I earned a badge!',
    });
  });

  it('includes url only when explicitly passed', async () => {
    const share = stubShare();
    const user = userEvent.setup();
    render(<ShareButton title="t" text="x" url="https://example.com" />);

    await user.click(screen.getByRole('button', { name: /share/i }));

    expect(share).toHaveBeenCalledWith({
      title: 't', text: 'x', url: 'https://example.com',
    });
  });

  it('swallows a dismissed share sheet', async () => {
    stubShare(vi.fn().mockRejectedValue(new DOMException('cancel', 'AbortError')));
    const user = userEvent.setup();
    render(<ShareButton title="t" text="x" />);

    // Must not throw / produce an unhandled rejection.
    await user.click(screen.getByRole('button', { name: /share/i }));
    expect(screen.getByRole('button', { name: /share/i })).toBeInTheDocument();
  });
});
