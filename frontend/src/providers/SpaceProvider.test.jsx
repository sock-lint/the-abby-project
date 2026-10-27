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
    <button onClick={() => getPendingRedemptions()}>Read family reviews</button>
    <ChapterBottomBar user={auth.user} />
  </>;
}

function tree(blocked = false) {
  return <MemoryRouter initialEntries={['/']}><PwaStatusContext.Provider value={{ updateBlocked: blocked }}>
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
