import { useEffect, useState } from 'react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/server';
import { buildParent, buildUser } from '../test/factories';
import { getDashboard, getPendingRedemptions } from '../api';
import { getToken, setToken } from '../api/client';
import { requestSpace } from '../api/space';
import { PwaStatusContext } from '../pwa/pwaStatus.context';
import SpaceProvider from './SpaceProvider';
import { useSpace } from '../hooks/useSpace';
import SpaceSwitcher from '../components/layout/SpaceSwitcher';
import { ChapterBottomBar } from '../components/layout/ChapterNav';

const auth = vi.hoisted(() => ({ user: null }));
vi.mock('../hooks/useApi', async importOriginal => ({ ...(await importOriginal()), useAuth: () => ({ user: auth.user }) }));
vi.mock('../hooks/useParentPendingCounts', () => ({ default: () => ({ total: 3, ready: true, incomplete: false }) }));

function Probe() {
  const { space, isParentAccount } = useSpace();
  const location = useLocation();
  const navigate = useNavigate();
  const [draft, setDraft] = useState('');
  const [payload, setPayload] = useState('');
  useEffect(() => {
    let mounted = true;
    getDashboard().then(data => { if (mounted) setPayload(data.space); });
    return () => { mounted = false; };
  }, []);
  return <>
    <SpaceSwitcher />
    <p data-testid="space">{space}</p><p data-testid="role">{isParentAccount ? 'parent' : 'child'}</p>
    <p data-testid="location">{location.pathname}{location.search}</p><p data-testid="payload">{payload}</p>
    <input aria-label="Local draft" value={draft} onChange={e => setDraft(e.target.value)} />
    <button onClick={() => navigate('/quests?tab=rituals')}>Open habits</button>
    <button onClick={() => navigate('/sigil')}>Open profile</button>
    <button onClick={() => getPendingRedemptions()}>Read family reviews</button>
    <ChapterBottomBar user={auth.user} />
  </>;
}

function tree(blocked = false, path = '/') {
  return <MemoryRouter initialEntries={[path]}><PwaStatusContext.Provider value={{ updateBlocked: blocked }}>
    <SpaceProvider><Probe /></SpaceProvider>
  </PwaStatusContext.Provider></MemoryRouter>;
}

describe('Family and My space as one unchanged parent identity', () => {
  beforeEach(() => {
    sessionStorage.clear();
    auth.user = buildParent({ id: 501 });
    server.use(http.get('*/api/dashboard/', ({ request }) => HttpResponse.json({ space: request.headers.get('X-Abby-Space') || 'family' })));
  });

  it('changes navigation and API scope, clears old view state, and retains parent identity', async () => {
    const user = userEvent.setup();
    render(tree());
    expect(await screen.findByTestId('payload')).toHaveTextContent('family');
    expect(screen.getByRole('link', { name: 'Children' })).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Pets' })).toBeNull();
    await user.type(screen.getByLabelText('Local draft'), 'Old workspace state');
    await user.click(screen.getByRole('button', { name: /^My space$/ }));
    await waitFor(() => expect(screen.getByTestId('payload')).toHaveTextContent('personal'));
    expect(screen.getByTestId('role')).toHaveTextContent('parent');
    expect(screen.getByLabelText('Local draft')).toHaveValue('');
    expect(screen.getByRole('link', { name: 'Pets' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Memories' })).toBeVisible();
    expect(screen.queryByRole('link', { name: 'Children' })).toBeNull();
    expect(screen.getByLabelText('3 family items needing attention')).toBeVisible();
    expect(requestSpace(getToken())).toBe('personal');
  });

  it('remembers the last route independently and keeps review reads on Family', async () => {
    const user = userEvent.setup();
    const scopes = [];
    server.use(http.get('*/api/redemptions/', ({ request }) => {
      scopes.push(request.headers.get('X-Abby-Space')); return HttpResponse.json([]);
    }));
    render(tree());
    await user.click(screen.getByRole('button', { name: 'Open habits' }));
    await user.click(screen.getByRole('button', { name: 'My space' }));
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/$/);
    await user.click(screen.getByRole('button', { name: 'Read family reviews' }));
    await waitFor(() => expect(scopes).toEqual([null]));
    await user.click(screen.getByRole('button', { name: /^Family/ }));
    expect(screen.getByTestId('location')).toHaveTextContent('/quests?tab=rituals');
  });

  it('blocks switching while a form has registered unfinished work', async () => {
    render(tree(true));
    expect(screen.getByRole('button', { name: 'My space' })).toBeDisabled();
    expect(screen.getByText(/Save or close your current form/)).toBeVisible();
    expect(screen.getByTestId('space')).toHaveTextContent('family');
  });

  it.each(['/quests?space=personal', '/bestiary?tab=mounts&space=personal'])(
    'opens a parent personal notification in the correct space from a new tab: %s', async (path) => {
      sessionStorage.setItem(`abby:spaces:${auth.user.family?.id}:${auth.user.id}`, JSON.stringify({ space: 'family' }));
      render(tree(false, path));
      await waitFor(() => expect(screen.getByTestId('payload')).toHaveTextContent('personal'));
      expect(screen.getByTestId('space')).toHaveTextContent('personal');
      expect(screen.getByTestId('role')).toHaveTextContent('parent');
      expect(screen.getByTestId('location')).toHaveTextContent(path);
      expect(requestSpace(getToken())).toBe('personal');
    },
  );

  it.each([
    '/quests?space=personal', '/bestiary?tab=mounts&space=personal',
    '/chores?space=personal', '/chronicle?tab=journal&space=personal', '/treasury?tab=hoards&space=personal',
    '/projects/123?space=personal',
  ])('persists a notification-selected personal space and its later route across reload: %s', async (path) => {
    const key = `abby:spaces:${auth.user.family?.id}:${auth.user.id}`;
    sessionStorage.setItem(key, JSON.stringify({ space: 'family', family: '/family' }));
    const user = userEvent.setup();
    const view = render(tree(false, path));
    await waitFor(() => expect(screen.getByTestId('payload')).toHaveTextContent('personal'));
    await user.click(screen.getByRole('button', { name: 'Open profile' }));
    expect(JSON.parse(sessionStorage.getItem(key))).toMatchObject({ space: 'personal', personal: '/sigil', family: '/family' });
    view.unmount();
    render(tree(false, '/sigil'));
    await waitFor(() => expect(screen.getByTestId('payload')).toHaveTextContent('personal'));
    expect(screen.getByTestId('role')).toHaveTextContent('parent');
  });

  it('starts and persists an explicit child journal link in Family despite a personal preference', async () => {
    const key = `abby:spaces:${auth.user.family?.id}:${auth.user.id}`;
    sessionStorage.setItem(key, JSON.stringify({ space: 'personal', personal: '/sigil' }));
    const path = '/chronicle?tab=grades&child=7&space=family';
    render(tree(false, path));
    await waitFor(() => expect(screen.getByTestId('payload')).toHaveTextContent('family'));
    expect(screen.getByTestId('location')).toHaveTextContent(path);
    expect(JSON.parse(sessionStorage.getItem(key))).toMatchObject({ space: 'family', family: path, personal: '/sigil' });
  });

  it.each(['/manage?space=personal', '/quests?space=unknown', '/quests?space=personal&space=family', '/chronicle?tab=grades&space=personal', '/treasury?tab=coffers&space=personal', '/projects/0?space=personal', '/projects/9007199254740992?space=personal', '/projects/new?space=personal'])(
    'keeps a parent Family launch for unsupported or ambiguous hints: %s', async (path) => {
      render(tree(false, path));
      await waitFor(() => expect(screen.getByTestId('payload')).toHaveTextContent('family'));
      expect(screen.getByTestId('space')).toHaveTextContent('family');
    },
  );

  it('keeps a notification-selected personal space while blocking a later switch with unfinished work', async () => {
    render(tree(true, '/chronicle?tab=journal&space=personal'));
    await waitFor(() => expect(screen.getByTestId('payload')).toHaveTextContent('personal'));
    expect(screen.getByRole('button', { name: /^Family/ })).toBeDisabled();
    expect(screen.getByText(/Save or close your current form/)).toBeVisible();
    expect(JSON.parse(sessionStorage.getItem(`abby:spaces:${auth.user.family?.id}:${auth.user.id}`)).space).toBe('personal');
  });

  it('ignores a child’s Family notification hint without changing role or transport authority', async () => {
    auth.user = buildUser();
    render(tree(false, '/chronicle?tab=journal&child=7&space=family'));
    await waitFor(() => expect(screen.getByTestId('payload')).toHaveTextContent('family'));
    expect(screen.getByTestId('space')).toHaveTextContent('personal');
    expect(screen.getByTestId('role')).toHaveTextContent('child');
    expect(requestSpace(getToken())).toBe('family');
    expect(screen.queryByRole('group', { name: 'Choose your space' })).toBeNull();
  });

  it.each(['/quests?space=personal', '/projects/123?space=personal'])('keeps a child personal launch without changing child API authority for a notification hint: %s', async (path) => {
    auth.user = buildUser();
    render(tree(false, path));
    await waitFor(() => expect(screen.getByTestId('payload')).toHaveTextContent('family'));
    expect(screen.getByTestId('space')).toHaveTextContent('personal');
    expect(screen.getByTestId('role')).toHaveTextContent('child');
    expect(requestSpace(getToken())).toBe('family');
  });

  it('does not offer children a Family space and never changes their role', async () => {
    auth.user = buildUser();
    render(tree());
    expect(screen.queryByRole('group', { name: 'Choose your space' })).toBeNull();
    expect(screen.getByTestId('space')).toHaveTextContent('personal');
    expect(screen.getByTestId('role')).toHaveTextContent('child');
    expect(screen.getByRole('link', { name: 'Pets' })).toBeVisible();
    expect(requestSpace(getToken())).toBe('family');
  });

  it('resets to the new account scope and never reuses another parent’s selection', async () => {
    const user = userEvent.setup();
    const view = render(tree());
    await user.click(screen.getByRole('button', { name: 'My space' }));
    auth.user = buildParent({ id: 502 });
    setToken('synthetic-next-parent-token');
    view.rerender(tree());
    expect(screen.getByTestId('space')).toHaveTextContent('family');
    expect(requestSpace(getToken())).toBe('family');
  });
});
