import { afterEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { AuthProvider } from './hooks/useApi';
import { server } from './test/server';
import { buildParent, buildProject, buildUser } from './test/factories';
import { emptyPulse } from './test/pulseFixtures';

vi.mock('framer-motion', async () => ({
  ...await vi.importActual('framer-motion'), AnimatePresence: ({ children }) => children,
}));

afterEach(() => { window.history.replaceState({}, '', '/'); });

const PROJECT = { link: '/projects/123?space=personal', canonical: '/quests/ventures/123', heading: 'My bookshelf' };
const CHORE = { link: '/chores?space=personal', canonical: '/quests?tab=duties', heading: 'Chores' };

function renderAccount(path, space = 'family', notifications = [], child = false) {
  const account = child ? buildUser({ id: 7, family: { id: 1 } }) : buildParent({ id: 90, family: { id: 1 } });
  sessionStorage.setItem(`abby:spaces:1:${account.id}`, JSON.stringify({ space }));
  window.history.replaceState({}, '', path);
  const scopes = [];
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(account)),
    http.get('*/api/pulse/', () => HttpResponse.json(emptyPulse({ notifications }))),
    http.get('*/api/notifications/pending-celebration/', () => HttpResponse.json(null)),
    http.get('*/api/projects/123/', ({ request }) => {
      scopes.push(request.headers.get('X-Abby-Space'));
      return HttpResponse.json(buildProject({ id: 123, title: PROJECT.heading, status: 'completed', assigned_to: account }));
    }),
    http.get('*/api/chores/', ({ request }) => {
      scopes.push(request.headers.get('X-Abby-Space'));
      return HttpResponse.json([]);
    }),
    http.get('*/api/children/', () => HttpResponse.json([])),
  );
  const user = userEvent.setup();
  render(<AuthProvider><App /></AuthProvider>);
  return { user, scopes };
}

async function expectDestination(destination, scopes, child = false) {
  await waitFor(() => {
    expect(window.location.pathname + window.location.search).toBe(destination.canonical);
    expect(screen.getAllByRole('heading', { name: destination.heading })[0]).toBeVisible();
  });
  if (child) {
    expect(screen.queryByRole('group', { name: 'Choose your space' })).not.toBeInTheDocument();
    expect(scopes).toContain(null);
    expect(scopes).not.toContain('personal');
  } else {
    expect(screen.getByRole('button', { name: 'My space' })).toHaveAttribute('aria-pressed', 'true');
    expect(scopes).toContain('personal');
  }
}

describe('Legacy receipt links through the actual App routes', () => {
  it.each([
    ['family', 'project_approved', PROJECT], ['personal', 'project_approved', PROJECT],
    ['family', 'milestone_completed', PROJECT], ['personal', 'milestone_completed', PROJECT],
    ['family', 'chore_approved', CHORE], ['personal', 'chore_approved', CHORE],
  ])('opens a parent %s inbox %s receipt as real page content', async (space, notificationType, destination) => {
    const { user, scopes } = renderAccount('/sigil', space, [{
      id: 18, notification_type: notificationType, title: 'Your work is complete', link: destination.link, is_read: true,
    }]);
    await waitFor(() => expect(screen.getByRole('button', { name: space === 'personal' ? 'My space' : /^Family/ })).toHaveAttribute('aria-pressed', 'true'));
    await user.click((await screen.findAllByRole('button', { name: /^Notifications/ }))[0]);
    await user.click(await screen.findByRole('button', { name: 'Your work is complete' }));
    await expectDestination(destination, scopes);
  });

  it.each([PROJECT, CHORE])('opens a hinted parent launch $link at its canonical page', async (destination) => {
    const { scopes } = renderAccount(destination.link);
    await expectDestination(destination, scopes);
  });

  it.each([PROJECT, CHORE])('preserves an unhinted parent legacy bookmark for $heading', async (destination) => {
    const { scopes } = renderAccount(destination.link.split('?')[0], 'personal');
    await expectDestination(destination, scopes);
  });

  it.each([PROJECT, CHORE])('keeps a child legacy launch $link on child authority', async (destination) => {
    const { scopes } = renderAccount(destination.link, 'family', [], true);
    await expectDestination(destination, scopes, true);
  });
});
