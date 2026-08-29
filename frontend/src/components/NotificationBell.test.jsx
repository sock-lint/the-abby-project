import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import NotificationBell from './NotificationBell.jsx';
import MockPulse from '../test/pulse.jsx';
import { emptyPulse } from '../test/pulseFixtures.js';
import { server } from '../test/server.js';

function setViewport(desktop) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: desktop && query.includes('min-width'),
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    onchange: null,
    dispatchEvent: vi.fn(),
  }));
}

/**
 * The bell reads both the unread count and the list off the shared heartbeat,
 * so tests seed a pulse rather than stubbing two endpoints on a timer.
 */
function renderBell({ desktop = true, notifications = [], unread = 0, pulse } = {}) {
  setViewport(desktop);
  const seeded = pulse === undefined
    ? emptyPulse({ notifications, unread_count: unread })
    : pulse;
  return render(
    <MockPulse pulse={seeded}>
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>
    </MockPulse>,
  );
}

afterEach(() => {
  vi.useRealTimers();
});

describe('NotificationBell', () => {
  it('closes when clicking outside (desktop popover only)', async () => {
    const user = userEvent.setup();
    const { container } = renderBell();
    await user.click(container.querySelector('button'));
    await waitFor(() => expect(screen.getByText(/all caught up/i)).toBeInTheDocument());
    const outside = document.createElement('div');
    document.body.appendChild(outside);
    act(() => {
      outside.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });
    await waitFor(() => expect(screen.queryByText(/all caught up/i)).toBeNull());
  });

  it('navigates when a notification has a link and closes the dropdown', async () => {
    const user = userEvent.setup();
    renderBell({
      unread: 1,
      notifications: [{ id: 7, title: 'go', is_read: true, link: '/quests', created_at: 'x' }],
    });
    await user.click(screen.getAllByRole('button')[0]);
    const row = await screen.findByText('go');
    await user.click(row);
    await waitFor(() => expect(screen.queryByText('go')).toBeNull());
  });

  it('renders the type-specific lucide icon for a known notification type', async () => {
    const user = userEvent.setup();
    const { container } = renderBell({
      unread: 1,
      notifications: [{
        id: 11, title: 'Sealed!', is_read: true,
        notification_type: 'badge_earned', link: '', created_at: 'x',
      }],
    });
    await user.click(screen.getAllByRole('button')[0]);
    await screen.findByText('Sealed!');
    // ``badge_earned`` maps to lucide's Award icon, which carries
    // ``.lucide-award`` on its rendered SVG. The Bell icon stays in the
    // header trigger; the row icon is the one we want.
    expect(container.querySelector('.lucide-award')).not.toBeNull();
  });

  it('falls back to the type-default route when link is empty', async () => {
    const user = userEvent.setup();
    renderBell({
      unread: 1,
      notifications: [{
        id: 9, title: 'Sealed!', is_read: true,
        notification_type: 'badge_earned', link: '', created_at: 'x',
      }],
    });
    await user.click(screen.getAllByRole('button')[0]);
    const row = await screen.findByText('Sealed!');
    // The type-default route closes the dropdown the same way an explicit
    // link would — that confirms a click was treated as navigation rather
    // than a no-op.
    await user.click(row);
    await waitFor(() => expect(screen.queryByText('Sealed!')).toBeNull());
  });

  it('renders the heartbeat list when opened', async () => {
    const user = userEvent.setup();
    renderBell({
      unread: 1,
      notifications: [{ id: 1, title: 'Hi', message: 'There', is_read: false, created_at: '2026-04-16T00:00:00Z' }],
    });
    await waitFor(() => expect(screen.getByText('1')).toBeInTheDocument());
    await user.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText('Hi')).toBeInTheDocument());
  });

  it('shows empty state when no notifications', async () => {
    const user = userEvent.setup();
    renderBell();
    await user.click(screen.getAllByRole('button')[0]);
    await waitFor(() => expect(screen.getByText(/all caught up/i)).toBeInTheDocument());
    expect(screen.getByText(/no new notifications/i)).toBeInTheDocument();
  });

  it('marks-all-read calls the API and clears the count', async () => {
    server.use(http.post('*/api/notifications/mark_all_read/', () => HttpResponse.json({})));
    const user = userEvent.setup();
    renderBell({
      unread: 2,
      notifications: [{ id: 1, title: 'a', is_read: false, created_at: 'x' }],
    });
    await user.click(screen.getAllByRole('button')[0]);
    const markAll = await screen.findByRole('button', { name: /mark all read/i });
    await user.click(markAll);
    await waitFor(() => expect(screen.queryByText('2')).toBeNull());
  });

  // Offline, the old handler rejected unhandled: no state updates ran and the
  // button read as a dead no-op with the badge still lit.
  it('rolls the badge back and says so when mark-all-read fails', async () => {
    server.use(http.post('*/api/notifications/mark_all_read/', () => HttpResponse.error()));
    const user = userEvent.setup();
    renderBell({
      unread: 2,
      notifications: [{ id: 1, title: 'a', is_read: false, created_at: 'x' }],
    });
    await user.click(screen.getAllByRole('button')[0]);
    const markAll = await screen.findByRole('button', { name: /mark all read/i });
    await user.click(markAll);
    expect(await screen.findByRole('alert')).toHaveTextContent(/try again/i);
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('marks a single notification read on click', async () => {
    server.use(http.post(/\/notifications\/5\/mark_read/, () => HttpResponse.json({})));
    const user = userEvent.setup();
    renderBell({
      unread: 1,
      notifications: [{ id: 5, title: 'clickable', is_read: false, created_at: 'x' }],
    });
    await user.click(screen.getAllByRole('button')[0]);
    const row = await screen.findByText('clickable');
    await user.click(row);
    await waitFor(() => expect(screen.queryByText('1')).toBeNull());
  });

  it('renders zero unread by default', async () => {
    renderBell();
    await waitFor(() => expect(screen.queryByText('0')).toBeNull());
  });

  it('shows the unread badge when count > 0', async () => {
    renderBell({ unread: 3 });
    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument());
  });

  it('clamps large counts to 9+', async () => {
    renderBell({ unread: 42 });
    await waitFor(() => expect(screen.getByText('9+')).toBeInTheDocument());
  });

  it('renders no badge before the first heartbeat lands', async () => {
    // A missed or not-yet-arrived beat must leave the bell quiet rather than
    // flashing a stale or zero badge.
    renderBell({ pulse: null });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/^[0-9]+$/)).toBeNull();
  });

  it('opens a bottom sheet instead of a popover on phones', async () => {
    const user = userEvent.setup();
    const { container } = renderBell({
      desktop: false,
      unread: 2,
      notifications: [
        { id: 1, title: 'Chore submitted', message: 'Dishes', is_read: false, created_at: '2026-08-20T10:00:00Z', notification_type: 'chore_submitted' },
      ],
    });
    await user.click(container.querySelector('button'));

    // A real sheet — full-width rows in the thumb zone rather than a 320px
    // dropdown pinned under the header.
    const sheet = await screen.findByRole('dialog', { name: /notifications/i });
    expect(sheet).toBeInTheDocument();
    expect(screen.getByText('Chore submitted')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /mark all read/i })).toBeInTheDocument();
  });
});
