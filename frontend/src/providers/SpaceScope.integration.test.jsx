import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor } from '../test/render';
import { server } from '../test/server';
import { buildParent } from '../test/factories';
import { api, getToken } from '../api/client';
import { setRequestSpace } from '../api/space';
import { useAuth } from '../hooks/useApi';
import { useSpace } from '../hooks/useSpace';
import useChildContext from '../hooks/useChildContext';
import { usePwaUpdateGuard } from '../pwa/usePwaUpdateGuard';
import { PwaStatusProvider } from '../pwa/PwaStatusProvider';
import SpaceProvider from './SpaceProvider';
import ParentReviewProvider from './ParentReviewProvider';
import SpaceSwitcher from '../components/layout/SpaceSwitcher';

const PARENT = buildParent({ id: 90, family: { id: 1 } });
const preferencesKey = 'abby:spaces:1:90';

function Probe() {
  const { user: account, login } = useAuth();
  const context = useChildContext();
  const { space } = useSpace();
  const navigate = useNavigate();
  const location = useLocation();
  const [draft, setDraft] = useState('');
  usePwaUpdateGuard(Boolean(draft));
  return <>
    <SpaceSwitcher />
    <span data-testid="identity">{space}:{account?.id}:{account?.role}:{context.targetUserId}</span>
    <span data-testid="route">{location.pathname}{location.search}</span>
    <input aria-label="Protected work" value={draft} onChange={(event) => setDraft(event.target.value)} />
    <button onClick={() => navigate('/quests?tab=rituals&child=7')}>Open family habits</button>
    <button onClick={() => navigate('/bestiary?tab=mounts')}>Personal pets</button>
    <button onClick={() => navigate('/chronicle?tab=journal&space=personal')}>Open hinted journal</button>
    <button onClick={() => void login('another-parent', 'synthetic-password')}>Sign in another parent</button>
  </>;
}

function renderSpaces(route = '/') {
  return renderWithProviders(<PwaStatusProvider><SpaceProvider><ParentReviewProvider><Probe /></ParentReviewProvider></SpaceProvider></PwaStatusProvider>, { route });
}

beforeEach(() => {
  sessionStorage.clear();
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(PARENT)),
    http.get('*/api/children/', () => HttpResponse.json([{ id: 7, username: 'abby' }])));
});

describe('Space boundaries with real account and review providers', () => {
  it('keeps every family review source and later pages in Family while showing My space', async () => {
    sessionStorage.setItem(preferencesKey, JSON.stringify({ space: 'personal' }));
    const reads = [];
    const source = (path, body) => http.get(`*/api/${path}`, ({ request }) => {
      reads.push({ path, scope: request.headers.get('X-Abby-Space'), url: new URL(request.url) });
      return HttpResponse.json(typeof body === 'function' ? body(request) : body);
    });
    server.use(
      source('chore-completions/', []), source('homework/dashboard/', { pending_submissions: [] }),
      source('redemptions/', []), source('dashboard/', {}), source('creations/pending/', []),
      source('chores/', []), source('habits/', []), source('print-requests/', []),
      source('coins/exchange/list/', (request) => {
        if (request.headers.get('X-Abby-Space')) return [];
        return new URL(request.url).searchParams.get('page') === '2'
          ? { results: [{ id: 8, user: 7, user_name: 'Abby', status: 'pending', dollar_amount: '1.00', coin_amount: 10 }], next: null }
          : { results: [], next: 'http://localhost/api/coins/exchange/list/?status=pending&page=2' };
      }),
    );
    renderSpaces('/bestiary');
    expect(await screen.findByLabelText('1 family items needing attention')).toBeInTheDocument();
    expect(screen.getByTestId('identity')).toHaveTextContent('personal:90:parent:90');
    expect(reads).toHaveLength(11);
    expect(reads.every((read) => read.scope === null)).toBe(true);
    expect(reads.some((read) => read.url.searchParams.get('page') === '2')).toBe(true);
  });

  it('blocks a real dirty form from switching and restores each space’s route after closing it', async () => {
    const { user } = renderSpaces('/quests?tab=rituals&child=7');
    await waitFor(() => expect(screen.getByTestId('identity')).toHaveTextContent('family:90:parent:7'));
    await user.type(screen.getByLabelText('Protected work'), 'Unfinished note');
    const personal = screen.getByRole('button', { name: 'My space' });
    expect(personal).toBeDisabled();
    await user.click(personal);
    expect(screen.getByTestId('identity')).toHaveTextContent('family:90:parent:7');
    await user.clear(screen.getByLabelText('Protected work'));
    await user.click(personal);
    expect(screen.getByTestId('identity')).toHaveTextContent('personal:90:parent:90');
    await user.click(screen.getByRole('button', { name: 'Personal pets' }));
    await user.click(screen.getByRole('button', { name: /^Family/ }));
    expect(screen.getByTestId('route')).toHaveTextContent('/quests?tab=rituals&child=7');
    await user.click(screen.getByRole('button', { name: 'My space' }));
    expect(screen.getByTestId('route')).toHaveTextContent('/bestiary?tab=mounts');
    expect(screen.getByTestId('route')).not.toHaveTextContent('child=');
  });

  it('reloads a persisted personal workspace with the matching account and self target', async () => {
    sessionStorage.setItem(preferencesKey, JSON.stringify({ space: 'personal', family: '/family?child=7', personal: '/quests?tab=reading' }));
    renderSpaces('/quests?tab=reading');
    await waitFor(() => expect(screen.getByTestId('identity')).toHaveTextContent('personal:90:parent:90'));
    expect(screen.getByTestId('route')).toHaveTextContent('/quests?tab=reading');
    expect(screen.getByRole('button', { name: 'My space' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps a real dirty form mounted when a later same-space hint arrives, then cleans the hint after closing it', async () => {
    sessionStorage.setItem(preferencesKey, JSON.stringify({ space: 'personal' }));
    const { user } = renderSpaces('/chronicle?tab=journal');
    await waitFor(() => expect(screen.getByTestId('identity')).toHaveTextContent('personal:90:parent:90'));
    await user.type(screen.getByLabelText('Protected work'), 'Unfinished personal note');
    expect(screen.getByRole('button', { name: /^Family/ })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Open hinted journal' }));
    expect(screen.getByLabelText('Protected work')).toHaveValue('Unfinished personal note');
    expect(screen.getByRole('button', { name: /^Family/ })).toBeDisabled();
    expect(screen.getByTestId('identity')).toHaveTextContent('personal:90:parent:90');
    await user.clear(screen.getByLabelText('Protected work'));
    await waitFor(() => expect(screen.getByTestId('route')).toHaveTextContent(/^\/chronicle\?tab=journal$/));
    expect(screen.getByTestId('identity')).toHaveTextContent('personal:90:parent:90');
  });

  it('discards the previous parent’s personal scope when the actual credential changes', async () => {
    sessionStorage.setItem(preferencesKey, JSON.stringify({ space: 'personal' }));
    const { user } = renderSpaces('/');
    await waitFor(() => expect(screen.getByTestId('identity')).toHaveTextContent('personal:90:parent:90'));
    server.use(http.post('*/api/auth/', () => HttpResponse.json({ ...buildParent({ id: 91, family: { id: 2 } }), token: 'another-synthetic-parent' })),
      http.get('*/api/children/', () => HttpResponse.json([{ id: 8, username: 'ben' }])));
    await user.click(screen.getByRole('button', { name: 'Sign in another parent' }));
    await waitFor(() => expect(screen.getByTestId('identity')).toHaveTextContent('family:91:parent:8'));
    expect(screen.getByRole('button', { name: /^Family/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps an old request’s retry on its captured scope after the selected space changes', async () => {
    const scopes = [];
    let release;
    let firstRead;
    const started = new Promise((resolve) => { firstRead = resolve; });
    const pending = new Promise((resolve) => { release = resolve; });
    server.use(http.get('*/api/scope-probe/', async ({ request }) => {
      scopes.push(request.headers.get('X-Abby-Space'));
      if (scopes.length === 1) {
        firstRead();
        await pending;
        return new HttpResponse('<html>Brief gateway page</html>', { headers: { 'Content-Type': 'text/html' } });
      }
      return HttpResponse.json({ okay: true });
    }));
    setRequestSpace('personal', getToken());
    const read = api.get('/scope-probe/');
    await started;
    setRequestSpace('family', getToken());
    release();
    await expect(read).resolves.toEqual({ okay: true });
    expect(scopes).toEqual(['personal', 'personal']);
  });
});
