import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server.js';
import PushNotificationsCard from './PushNotificationsCard.jsx';

const REAL_SW = navigator.serviceWorker;

function installPushApis({ permission = 'default', existing = null, grant = 'granted' } = {}) {
  const subscription = {
    endpoint: 'https://push.example/abc',
    toJSON: () => ({ endpoint: 'https://push.example/abc', keys: { p256dh: 'p', auth: 'a' } }),
    unsubscribe: vi.fn().mockResolvedValue(true),
  };
  Object.defineProperty(navigator, 'serviceWorker', {
    value: {
      ready: Promise.resolve({
        pushManager: {
          getSubscription: vi.fn().mockResolvedValue(existing),
          subscribe: vi.fn().mockResolvedValue(subscription),
        },
      }),
    },
    configurable: true,
  });
  window.PushManager = function PushManagerStub() {};
  window.Notification = {
    permission,
    requestPermission: vi.fn().mockResolvedValue(grant),
  };
}

function serverEnabled(enabled = true) {
  server.use(
    http.get('*/api/push/config/', () =>
      HttpResponse.json({ enabled, public_key: enabled ? 'BEl62iUYgUivxIkv69yViEuiBIa40HI' : '' }),
    ),
  );
}

beforeEach(() => installPushApis());

afterEach(() => {
  Object.defineProperty(navigator, 'serviceWorker', { value: REAL_SW, configurable: true });
  delete window.PushManager;
  delete window.Notification;
  vi.restoreAllMocks();
});

describe('PushNotificationsCard', () => {
  it('renders nothing when the server has no VAPID keypair', async () => {
    serverEnabled(false);
    const { container } = render(<PushNotificationsCard />);
    // Offering a button that cannot work is worse than staying quiet.
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('offers to turn notifications on when none are registered', async () => {
    serverEnabled();
    render(<PushNotificationsCard />);
    expect(
      await screen.findByRole('button', { name: /turn on notifications/i }),
    ).toBeInTheDocument();
  });

  it('offers to turn them off once this device is subscribed', async () => {
    serverEnabled();
    installPushApis({ permission: 'granted', existing: { endpoint: 'https://push.example/abc' } });
    render(<PushNotificationsCard />);
    expect(
      await screen.findByRole('button', { name: /turn off on this device/i }),
    ).toBeInTheDocument();
  });

  it('subscribing flips the card to the on state', async () => {
    serverEnabled();
    const user = userEvent.setup();
    render(<PushNotificationsCard />);
    await user.click(await screen.findByRole('button', { name: /turn on notifications/i }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /turn off on this device/i })).toBeInTheDocument(),
    );
  });

  it('explains how to recover when the browser has blocked notifications', async () => {
    serverEnabled();
    installPushApis({ permission: 'denied' });
    render(<PushNotificationsCard />);
    // Only the browser's own settings can undo a denial — say so rather than
    // showing a button that will silently no-op.
    expect(await screen.findByText(/blocked for this site/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /turn on notifications/i })).toBeNull();
  });

  it('tells iPhone users to install the app first when push APIs are missing', async () => {
    serverEnabled();
    Object.defineProperty(navigator, 'serviceWorker', { value: undefined, configurable: true });
    delete window.PushManager;
    render(<PushNotificationsCard />);
    expect(await screen.findByText(/add the app to your home screen/i)).toBeInTheDocument();
  });
});
