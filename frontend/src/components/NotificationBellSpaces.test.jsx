import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildParent } from '../test/factories';
import { emptyPulse } from '../test/pulseFixtures';
import MockPulse from '../test/pulse';
import { AuthProvider, useAuth } from '../hooks/useApi';
import { useSpace } from '../hooks/useSpace';
import { PwaStatusContext } from '../pwa/pwaStatus.context';
import SpaceProvider from '../providers/SpaceProvider';
import NotificationBell from './NotificationBell';

const pulse = emptyPulse({ unread_count: 1, notifications: [{ id: 17, notification_type: 'streak_at_risk', title: 'Keep your own streak', link: '/quests', is_read: false }] });
function Probe() {
  const { pathname, search } = useLocation();
  const { space } = useSpace();
  const { user } = useAuth();
  return <><output aria-label="Current page">{pathname}{search}</output><output aria-label="Current space">{space}</output><output aria-label="Account role">{user?.role}</output></>;
}
function tree(blocked, seededPulse = pulse) {
  return <MemoryRouter initialEntries={['/projects/new']}><AuthProvider><PwaStatusContext.Provider value={{ updateBlocked: blocked }}><MockPulse pulse={seededPulse}><SpaceProvider><NotificationBell /><Probe /></SpaceProvider></MockPulse></PwaStatusContext.Provider></AuthProvider></MemoryRouter>;
}

beforeEach(() => {
  sessionStorage.clear();
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
});

describe('Notification navigation with unfinished work', () => {
  it.each([['desktop', true], ['mobile', false]])('opens an own-parent project completion in My space from the %s inbox', async (_name, desktop) => {
    window.matchMedia = vi.fn(query => ({ matches: desktop && query.includes('min-width'), media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn() }));
    const user = userEvent.setup();
    render(tree(false, emptyPulse({ notifications: [{ id: 18, notification_type: 'project_approved', title: 'Project completed: My bookshelf', link: '/projects/123?space=personal', is_read: true }] })));
    await waitFor(() => expect(screen.getByRole('status', { name: 'Account role' })).toHaveTextContent('parent'));
    await user.click(screen.getByRole('button', { name: 'Notifications' }));
    await user.click(await screen.findByRole('button', { name: 'Project completed: My bookshelf' }));
    await waitFor(() => expect(screen.getByRole('status', { name: 'Current space' })).toHaveTextContent('personal'));
    expect(screen.getByRole('status', { name: 'Current page' })).toHaveTextContent('/projects/123?space=personal');
    expect(screen.getByRole('status', { name: 'Account role' })).toHaveTextContent('parent');
  });

  it.each([['desktop', true], ['mobile', false]])('keeps the %s notification unread and open when a space switch is refused, then retries after saving', async (_name, desktop) => {
    window.matchMedia = vi.fn(query => ({ matches: desktop && query.includes('min-width'), media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn() }));
    const mark = spyHandler('post', /\/api\/notifications\/17\/mark_read\/$/, {});
    server.use(mark.handler);
    const user = userEvent.setup();
    const view = render(tree(true));
    await waitFor(() => expect(screen.getByRole('status', { name: 'Account role' })).toHaveTextContent('parent'));
    await user.click(await screen.findByRole('button', { name: 'Notifications (1 unread)' }));
    await user.click(await screen.findByRole('button', { name: 'Keep your own streak' }));
    const inbox = await screen.findByRole(desktop ? 'region' : 'dialog', { name: 'Notifications' });
    expect(within(inbox).getByRole('alert')).toHaveTextContent('Save or close your current form, then try this notification again.');
    expect(screen.getByRole('status', { name: 'Current page' })).toHaveTextContent('/projects/new');
    expect(screen.getByRole('status', { name: 'Current space' })).toHaveTextContent('family');
    expect(screen.getByRole('button', { name: 'Notifications (1 unread)' })).toBeInTheDocument();
    expect(mark.calls).toHaveLength(0);

    view.rerender(tree(false));
    await user.click(screen.getByRole('button', { name: 'Keep your own streak' }));
    await waitFor(() => expect(screen.getByRole('status', { name: 'Current space' })).toHaveTextContent('personal'));
    expect(screen.getByRole('status', { name: 'Current page' })).toHaveTextContent(/^\/quests$/);
    expect(screen.getByRole('status', { name: 'Account role' })).toHaveTextContent('parent');
    await waitFor(() => expect(mark.calls).toHaveLength(1));
    expect(screen.queryByRole(desktop ? 'region' : 'dialog', { name: 'Notifications' })).not.toBeInTheDocument();
  });
});
