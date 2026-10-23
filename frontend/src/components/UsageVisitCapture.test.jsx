import { StrictMode } from 'react';
import { Link } from 'react-router-dom';
import { http, HttpResponse } from 'msw';
import { act, renderWithProviders, screen, waitFor } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildUser } from '../test/factories';
import { useAuth } from '../hooks/useApi';
import UsageVisitCapture from './UsageVisitCapture';

let sequence = 0;
beforeEach(() => {
  localStorage.setItem('abby_auth_token', `visit-test-session-${++sequence}`);
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())));
});
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

function SwitchAccount() {
  const { setUser } = useAuth();
  return <button onClick={() => {
    localStorage.setItem('abby_auth_token', `replacement-visit-session-${sequence}`);
    setUser(buildUser({ id: 2, family: { id: 2 } }));
  }}>Switch account</button>;
}

function CollectionPolicySwitch() {
  const { user, setUser } = useAuth();
  return <button disabled={!user} onClick={() => setUser({ ...user, usage_collection_enabled: user.usage_collection_enabled === false })}>
    {user?.usage_collection_enabled === false ? 'Enable measurement' : 'Pause measurement'}
  </button>;
}

describe('Usage visit capture', () => {
  it('sends no visit POST for a server-excluded observer identity, including navigation and visibility changes', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ usage_collection_enabled: false }))));
    const spy = spyHandler('post', '*/api/usage/visit/', { recorded: true });
    server.use(spy.handler);
    const { user } = renderWithProviders(<><UsageVisitCapture /><CollectionPolicySwitch /><Link to="/quests">Open tasks</Link></>);
    await screen.findByRole('button', { name: 'Enable measurement' });
    await user.click(screen.getByRole('link', { name: 'Open tasks' }));
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await act(async () => {});
    expect(spy.calls).toHaveLength(0);
  });

  it('honors a current account collection-policy change without marking an excluded visit attempted', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-23T12:00:00Z'));
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser({ usage_collection_enabled: false }))));
    const spy = spyHandler('post', '*/api/usage/visit/', { recorded: true });
    server.use(spy.handler);
    const { user } = renderWithProviders(<><UsageVisitCapture /><CollectionPolicySwitch /></>);
    await user.click(await screen.findByRole('button', { name: 'Enable measurement' }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    await user.click(screen.getByRole('button', { name: 'Pause measurement' }));
    vi.setSystemTime(new Date('2026-10-24T12:00:00Z'));
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await act(async () => {});
    expect(spy.calls).toHaveLength(1);
  });

  it('records only one body-free visit across StrictMode and private route navigation', async () => {
    const spy = spyHandler('post', '*/api/usage/visit/', { recorded: true });
    server.use(spy.handler);
    const { user } = renderWithProviders(<StrictMode><UsageVisitCapture /><Link to="/chronicle?tab=journal&entry=synthetic-private-note#content">Open journal</Link></StrictMode>);
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    await user.click(screen.getByRole('link', { name: 'Open journal' }));
    await act(async () => {});
    expect(spy.calls).toHaveLength(1);
    expect(spy.calls[0].body).toEqual({});
    expect(spy.calls[0].url).toMatch(/\/api\/usage\/visit\/$/);
    expect(spy.calls[0].url).not.toContain('journal');
  });

  it('waits for a visible foreground before recording', async () => {
    const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    const spy = spyHandler('post', '*/api/usage/visit/', { recorded: true });
    server.use(spy.handler);
    renderWithProviders(<UsageVisitCapture />);
    await act(async () => {});
    expect(spy.calls).toHaveLength(0);
    visibility.mockReturnValue('visible');
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    expect(spy.calls).toHaveLength(1);
  });

  it('does not automatically retry an uncertain failed POST', async () => {
    let calls = 0;
    server.use(http.post('*/api/usage/visit/', () => { calls++; return HttpResponse.error(); }));
    const { user } = renderWithProviders(<><UsageVisitCapture /><Link to="/quests">Open tasks</Link></>);
    await waitFor(() => expect(calls).toBe(1));
    await user.click(screen.getByRole('link', { name: 'Open tasks' }));
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await act(async () => {});
    expect(calls).toBe(1);
  });

  it('records the new authenticated account with no actor supplied in the body', async () => {
    const identities = [];
    server.use(http.post('*/api/usage/visit/', async ({ request }) => {
      identities.push({ authorization: request.headers.get('authorization'), body: await request.json() });
      return HttpResponse.json({ recorded: true });
    }));
    const { user } = renderWithProviders(<><UsageVisitCapture /><SwitchAccount /></>);
    await waitFor(() => expect(identities).toHaveLength(1));
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    await waitFor(() => expect(identities).toHaveLength(2));
    expect(identities[1]).toEqual({ authorization: `Token replacement-visit-session-${sequence}`, body: {} });
  });

  it('records a new UTC day after foreground visibility resumes without background polling', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-10-23T23:59:00Z'));
    const spy = spyHandler('post', '*/api/usage/visit/', { recorded: true });
    server.use(spy.handler);
    renderWithProviders(<UsageVisitCapture />);
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    vi.setSystemTime(new Date('2026-10-24T00:01:00Z'));
    await act(async () => {});
    expect(spy.calls).toHaveLength(1);
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    await waitFor(() => expect(spy.calls).toHaveLength(2));
  });

  it.each(['/login', '/signup', '/__design'])('does not collect public route %s', async (route) => {
    let calls = 0;
    server.use(http.post('*/api/usage/visit/', () => { calls++; return HttpResponse.json({ recorded: true }); }));
    renderWithProviders(<UsageVisitCapture />, { route });
    await act(async () => {});
    expect(calls).toBe(0);
  });

  it('does not collect without an authenticated identity', async () => {
    localStorage.removeItem('abby_auth_token');
    let calls = 0;
    server.use(http.post('*/api/usage/visit/', () => { calls++; return HttpResponse.json({ recorded: true }); }));
    renderWithProviders(<UsageVisitCapture />);
    await act(async () => {});
    expect(calls).toBe(0);
  });
});
