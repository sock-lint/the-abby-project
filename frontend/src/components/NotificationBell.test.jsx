import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import NotificationBell from './NotificationBell.jsx';
import { server } from '../test/server.js';

function renderBell() {
  return render(
    <MemoryRouter>
      <NotificationBell />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.useRealTimers();
});

describe('NotificationBell (real timers)', () => {
  it('closes when clicking outside', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () => HttpResponse.json({ count: 0 })),
      http.get('*/api/notifications/', () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    const { container } = renderBell();
    await user.click(container.querySelector('button'));
    await waitFor(() => expect(screen.getByText(/no notifications/i)).toBeInTheDocument());
    const outside = document.createElement('div');
    document.body.appendChild(outside);
    act(() => {
      outside.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    });
    await waitFor(() => expect(screen.queryByText(/no notifications/i)).toBeNull());
  });

  it('navigates when a notification has a link and closes dropdown', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () => HttpResponse.json({ count: 1 })),
      http.get('*/api/notifications/', () =>
        HttpResponse.json([{ id: 7, title: 'go', is_read: true, link: '/quests', created_at: 'x' }]),
      ),
    );
    const user = userEvent.setup();
    renderBell();
    await user.click(screen.getAllByRole('button')[0]);
    const row = await screen.findByText('go');
    await user.click(row);
    await waitFor(() => expect(screen.queryByText('go')).toBeNull());
  });

  it('renders the type-specific lucide icon for a known notification type', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () => HttpResponse.json({ count: 1 })),
      http.get('*/api/notifications/', () =>
        HttpResponse.json([{
          id: 11, title: 'Sealed!', is_read: true,
          notification_type: 'badge_earned', link: '', created_at: 'x',
        }]),
      ),
    );
    const user = userEvent.setup();
    const { container } = renderBell();
    await user.click(screen.getAllByRole('button')[0]);
    await screen.findByText('Sealed!');
    // ``badge_earned`` maps to lucide's Award icon, which carries
    // ``.lucide-award`` on its rendered SVG. The Bell icon stays in the
    // header trigger; the row icon is the one we want.
    const rowIcon = container.querySelector('.lucide-award');
    expect(rowIcon).not.toBeNull();
  });

  it('falls back to the type-default route when link is empty', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () => HttpResponse.json({ count: 1 })),
      http.get('*/api/notifications/', () =>
        HttpResponse.json([{
          id: 9, title: 'Sealed!', is_read: true,
          notification_type: 'badge_earned', link: '', created_at: 'x',
        }]),
      ),
    );
    const user = userEvent.setup();
    renderBell();
    await user.click(screen.getAllByRole('button')[0]);
    const row = await screen.findByText('Sealed!');
    // The type-default route closes the dropdown the same way an explicit
    // link would — that confirms a click was treated as navigation rather
    // than a no-op.
    await user.click(row);
    await waitFor(() => expect(screen.queryByText('Sealed!')).toBeNull());
  });

  it('opens the dropdown and loads notifications on click', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () => HttpResponse.json({ count: 1 })),
      http.get('*/api/notifications/', () =>
        HttpResponse.json([{ id: 1, title: 'Hi', message: 'There', is_read: false, created_at: '2026-04-16T00:00:00Z' }]),
      ),
    );
    const user = userEvent.setup();
    renderBell();
    await waitFor(() => expect(screen.getByText('1')).toBeInTheDocument());
    await user.click(screen.getByRole('button'));
    await waitFor(() => expect(screen.getByText('Hi')).toBeInTheDocument());
  });

  it('shows empty state when no notifications', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () => HttpResponse.json({ count: 0 })),
      http.get('*/api/notifications/', () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    renderBell();
    await user.click(screen.getAllByRole('button')[0]);
    await waitFor(() => expect(screen.getByText(/no notifications/i)).toBeInTheDocument());
  });

  it('marks-all-read calls the API and clears the count', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () => HttpResponse.json({ count: 2 })),
      http.get('*/api/notifications/', () =>
        HttpResponse.json([{ id: 1, title: 'a', is_read: false, created_at: 'x' }]),
      ),
      http.post('*/api/notifications/mark_all_read/', () => HttpResponse.json({})),
    );
    const user = userEvent.setup();
    renderBell();
    await user.click(screen.getAllByRole('button')[0]);
    const markAll = await screen.findByRole('button', { name: /mark all read/i });
    await user.click(markAll);
    await waitFor(() => expect(screen.queryByText('2')).toBeNull());
  });

  it('marks a single notification read on click', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () => HttpResponse.json({ count: 1 })),
      http.get('*/api/notifications/', () =>
        HttpResponse.json([{ id: 5, title: 'clickable', is_read: false, created_at: 'x' }]),
      ),
      http.post(/\/notifications\/5\/mark_read/, () => HttpResponse.json({})),
    );
    const user = userEvent.setup();
    renderBell();
    await user.click(screen.getAllByRole('button')[0]);
    const row = await screen.findByText('clickable');
    await user.click(row);
    await waitFor(() => expect(screen.queryByText('1')).toBeNull());
  });

  it('renders zero unread by default', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () =>
        HttpResponse.json({ count: 0 }),
      ),
    );
    renderBell();
    await waitFor(() => expect(screen.queryByText('0')).toBeNull());
  });

  it('shows the unread badge when count > 0', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () =>
        HttpResponse.json({ count: 3 }),
      ),
    );
    renderBell();
    await waitFor(() => expect(screen.getByText('3')).toBeInTheDocument());
  });

  it('clamps large counts to 9+', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () =>
        HttpResponse.json({ count: 42 }),
      ),
    );
    renderBell();
    await waitFor(() => expect(screen.getByText('9+')).toBeInTheDocument());
  });

  it('silently swallows count fetch errors', async () => {
    server.use(
      http.get('*/api/notifications/unread_count/', () =>
        HttpResponse.json({ error: 'boom' }, { status: 500 }),
      ),
    );
    renderBell();
    // No badge should render after the fetch fails.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByText(/^[0-9]+$/)).toBeNull();
  });
});

describe('NotificationBell polling (fake timers)', () => {
  it('polls the unread count at 30s intervals', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let calls = 0;
    server.use(
      http.get('*/api/notifications/unread_count/', () => {
        calls += 1;
        return HttpResponse.json({ count: calls });
      }),
    );
    const { unmount } = renderBell();
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(1));
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(2));
    unmount();
  });
});
