import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InstallCard from './InstallCard';
import * as installPromptModule from './useInstallPrompt';

function mockHook(value) {
  vi.spyOn(installPromptModule, 'useInstallPrompt').mockReturnValue(value);
}

const ORIGINAL_UA = window.navigator.userAgent;
const ORIGINAL_TOUCH_POINTS = window.navigator.maxTouchPoints;

// iPadOS 13+ Safari reports this desktop-class UA — identical to a real Mac's
// apart from maxTouchPoints, which is why the card has to sniff both.
const IPAD_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15';

function setUserAgent(ua) {
  Object.defineProperty(window.navigator, 'userAgent', {
    value: ua,
    configurable: true,
  });
}

function setMaxTouchPoints(n) {
  Object.defineProperty(window.navigator, 'maxTouchPoints', {
    value: n,
    configurable: true,
  });
}

describe('InstallCard', () => {
  beforeEach(() => {
    setUserAgent('Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0');
    setMaxTouchPoints(0);
  });
  afterEach(() => {
    setUserAgent(ORIGINAL_UA);
    setMaxTouchPoints(ORIGINAL_TOUCH_POINTS);
    vi.restoreAllMocks();
  });

  it('renders nothing when isStandalone is true', () => {
    mockHook({ canInstall: false, install: vi.fn(), isStandalone: true });
    const { container } = render(<InstallCard />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders the Install button when canInstall is true', async () => {
    const install = vi.fn(() => Promise.resolve({ outcome: 'accepted' }));
    mockHook({ canInstall: true, install, isStandalone: false });
    const user = userEvent.setup();
    render(<InstallCard />);
    const button = screen.getByRole('button', { name: /install app/i });
    expect(button).toBeInTheDocument();
    await user.click(button);
    expect(install).toHaveBeenCalledTimes(1);
  });

  it('renders iOS instructions on iPhone Safari without canInstall', () => {
    setUserAgent(
      'Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) AppleWebKit/605.1.15 Version/16.4 Mobile/15E148 Safari/604.1',
    );
    mockHook({ canInstall: false, install: vi.fn(), isStandalone: false });
    render(<InstallCard />);
    expect(screen.queryByRole('button', { name: /install app/i })).not.toBeInTheDocument();
    expect(screen.getByText(/share/i)).toBeInTheDocument();
    expect(screen.getByText(/add to home screen/i)).toBeInTheDocument();
  });

  // Regression: iPads reported a desktop Macintosh UA, missed both the iOS and
  // the Android branch, and got told their browser can't install the app —
  // even though Share → Add to Home Screen is exactly what they need.
  it('renders iOS instructions on iPadOS Safari (desktop-class UA)', () => {
    setUserAgent(IPAD_UA);
    setMaxTouchPoints(5);
    mockHook({ canInstall: false, install: vi.fn(), isStandalone: false });
    render(<InstallCard />);
    expect(screen.queryByText(/your browser doesn/i)).not.toBeInTheDocument();
    expect(screen.getByText(/share/i)).toBeInTheDocument();
    expect(screen.getByText(/add to home screen/i)).toBeInTheDocument();
  });

  it('still shows the generic fallback on desktop Mac Safari (no touch points)', () => {
    setUserAgent(IPAD_UA);
    setMaxTouchPoints(0);
    mockHook({ canInstall: false, install: vi.fn(), isStandalone: false });
    render(<InstallCard />);
    expect(screen.getByText(/your browser doesn/i)).toBeInTheDocument();
    expect(screen.queryByText(/add to home screen/i)).not.toBeInTheDocument();
  });

  it('renders Chrome menu instructions on Android Chrome without canInstall', () => {
    setUserAgent(
      'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    );
    mockHook({ canInstall: false, install: vi.fn(), isStandalone: false });
    render(<InstallCard />);
    expect(screen.queryByRole('button', { name: /install app/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/your browser doesn/i)).not.toBeInTheDocument();
    expect(screen.getByText(/tap the menu/i)).toBeInTheDocument();
    expect(screen.getByText(/add to home screen/i)).toBeInTheDocument();
  });

  it('renders the generic unsupported fallback on desktop Firefox', () => {
    setUserAgent(
      'Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0',
    );
    mockHook({ canInstall: false, install: vi.fn(), isStandalone: false });
    render(<InstallCard />);
    expect(screen.queryByRole('button', { name: /install app/i })).not.toBeInTheDocument();
    expect(screen.getByText(/your browser doesn/i)).toBeInTheDocument();
  });

  it('does NOT show the Chrome menu card on Samsung Internet (Android)', () => {
    setUserAgent(
      'Mozilla/5.0 (Linux; Android 14; SM-S911U) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0.0.0 Mobile Safari/537.36',
    );
    mockHook({ canInstall: false, install: vi.fn(), isStandalone: false });
    render(<InstallCard />);
    expect(screen.queryByText(/tap the menu/i)).not.toBeInTheDocument();
    expect(screen.getByText(/your browser doesn/i)).toBeInTheDocument();
  });
});
