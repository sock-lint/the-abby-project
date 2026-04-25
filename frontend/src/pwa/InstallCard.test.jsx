import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InstallCard from './InstallCard';
import * as installPromptModule from './useInstallPrompt';

function mockHook(value) {
  vi.spyOn(installPromptModule, 'useInstallPrompt').mockReturnValue(value);
}

const ORIGINAL_UA = window.navigator.userAgent;

function setUserAgent(ua) {
  Object.defineProperty(window.navigator, 'userAgent', {
    value: ua,
    configurable: true,
  });
}

describe('InstallCard', () => {
  beforeEach(() => {
    setUserAgent('Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0');
  });
  afterEach(() => {
    setUserAgent(ORIGINAL_UA);
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

  it('renders the unsupported fallback when not installable and not iOS', () => {
    mockHook({ canInstall: false, install: vi.fn(), isStandalone: false });
    render(<InstallCard />);
    expect(screen.queryByRole('button', { name: /install app/i })).not.toBeInTheDocument();
    expect(screen.getByText(/your browser/i)).toBeInTheDocument();
  });
});
