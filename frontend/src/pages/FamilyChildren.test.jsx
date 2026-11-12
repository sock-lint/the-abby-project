import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { useLocation } from 'react-router-dom';
import { act, renderWithProviders, screen, waitFor, within } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildParent, buildUser } from '../test/factories';
import { selectDropdown } from '../test/selectDropdown';
import { SpaceContext } from '../providers/spaceContext';
import FamilyChildren from './FamilyChildren';

vi.mock('framer-motion', async () => ({
  ...await vi.importActual('framer-motion'), AnimatePresence: ({ children }) => children,
}));

const CHILDREN = [buildUser({ id: 7, display_name: 'Abby' }), buildUser({ id: 8, display_name: 'Ben' })];
function overview(id = 7) {
  return { child: { id, display_name: id === 7 ? 'Abby' : 'Ben' }, level: id === 7 ? 3 : 5, coin_balance: id === 7 ? 45 : 80,
    skills: [{ id, skill_name: id === 7 ? 'Painting' : 'Woodworking', level: 2, xp_points: 25 }],
    badges: [{ id, badge: { id, name: id === 7 ? 'First painting' : 'First build' } }],
    pets: [{ id, species: { name: 'Fox', slug: 'fox', sprite_key: 'fox' }, potion: { name: 'Base', slug: 'base' }, name: id === 7 ? 'Sunny' : 'Maple', is_active: true }],
    mounts: [],
  };
}
function LocationProbe() { const location = useLocation(); return <span data-testid="location">{location.pathname}{location.search}</span>; }

function renderFamily({ account = buildParent({ family: { id: 1 } }), children = CHILDREN, route = '/family', personal = false } = {}) {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(account)),
    http.get('*/api/children/', () => HttpResponse.json(children)));
  return renderWithProviders(<SpaceContext.Provider value={{
    space: personal ? 'personal' : 'family',
    isParentAccount: account.role === 'parent', isPersonalSpace: personal || account.role === 'child',
    isFamilySpace: !personal && account.role === 'parent', switchSpace: vi.fn(),
  }}><FamilyChildren /><LocationProbe /></SpaceContext.Provider>, { route });
}

describe('Family Children', () => {
  it('reads a roster-verified child overview and links its tasks and shared memories without care controls', async () => {
    const read = spyHandler('get', /\/api\/children\/7\/overview\/$/, overview());
    server.use(read.handler);
    renderFamily({ route: '/family?child=999' });
    expect(await screen.findByRole('heading', { level: 2, name: 'Abby' })).toBeInTheDocument();
    expect(screen.getByText('Painting')).toBeInTheDocument();
    expect(screen.getByText('First painting')).toBeInTheDocument();
    expect(screen.getByText('Sunny')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View tasks' })).toHaveAttribute('href', '/quests?child=7');
    expect(screen.getByRole('link', { name: 'Shared memories' })).toHaveAttribute('href', '/chronicle?tab=journal&child=7');
    expect(screen.queryByRole('button', { name: /feed|activate|adjust coins|give xp/i })).toBeNull();
    expect(read.calls).toHaveLength(1);
    expect(read.calls[0]).toMatchObject({ method: 'GET', body: null });
    expect(read.calls[0].url).toMatch(/\/api\/children\/7\/overview\/$/);
  });

  it('clears the previous child’s progress while loading the newly selected child', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const abby = spyHandler('get', /\/api\/children\/7\/overview\/$/, overview(7));
    const ben = spyHandler('get', /\/api\/children\/8\/overview\/$/, async () => { await pending; return overview(8); });
    server.use(abby.handler, ben.handler);
    const { user } = renderFamily();
    await screen.findByText('Painting');
    await selectDropdown(user, screen.getByLabelText('Viewing'), '8');
    await waitFor(() => expect(ben.calls).toHaveLength(1));
    expect(screen.queryByText('Painting')).toBeNull();
    expect(screen.queryByText('First painting')).toBeNull();
    expect(screen.queryByText('Sunny')).toBeNull();
    await act(async () => { release(); await pending; });
    expect(await screen.findByText('Woodworking')).toBeInTheDocument();
    expect(screen.getByText('First build')).toBeInTheDocument();
    expect(screen.getByText('Maple')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View tasks' })).toHaveAttribute('href', '/quests?child=8');
  });

  it('keeps an unavailable overview distinct from empty earned progress and retries it', async () => {
    const read = spyHandler('get', /\/api\/children\/7\/overview\/$/, () => read.calls.length === 1
      ? HttpResponse.json({ detail: 'Child overview is temporarily unavailable.' }, { status: 503 }) : overview());
    server.use(read.handler);
    const { user } = renderFamily();
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Child overview is temporarily unavailable.');
    expect(screen.queryByText('No badges earned yet.')).toBeNull();
    await user.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('First painting')).toBeInTheDocument();
    expect(read.calls).toHaveLength(2);
  });

  it('rejects an overview whose identity does not match the selected child', async () => {
    server.use(http.get('*/api/children/7/overview/', () => HttpResponse.json(overview(8))));
    renderFamily();
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not verify this child’s overview.');
    expect(screen.queryByText('Woodworking')).toBeNull();
  });

  it('labels a bounded collection with its server-confirmed total', async () => {
    server.use(http.get('*/api/children/7/overview/', () => HttpResponse.json({
      ...overview(), counts: { skills: 12 },
      skills: Array.from({ length: 10 }, (_, i) => ({ id: i, skill_name: `Saved skill ${i + 1}`, level: 1, xp_points: 10 })),
    })));
    renderFamily();
    const skills = await screen.findByRole('region', { name: 'Skills' });
    expect(within(skills).getByText('Showing 8 of 12.')).toBeInTheDocument();
    expect(within(skills).getAllByRole('listitem')).toHaveLength(8);
    expect(within(skills).queryByText('Saved skill 9')).toBeNull();
  });

  it('shows family setup only after confirming an empty roster', async () => {
    const read = spyHandler('get', /\/api\/children\/\d+\/overview\/$/, overview());
    server.use(read.handler);
    renderFamily({ children: [] });
    expect(await screen.findByText('Add a child to see their progress here.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Manage family' })).toHaveAttribute('href', '/manage');
    expect(read.calls).toHaveLength(0);
  });

  it.each(['child', 'personal parent'])('redirects a %s away from Family Children without reading a child overview', async (accountKind) => {
    const read = spyHandler('get', /\/api\/children\/\d+\/overview\/$/, overview());
    server.use(read.handler);
    renderFamily({ account: accountKind === 'child' ? buildUser() : buildParent(), personal: accountKind !== 'child' });
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(/^\/$/));
    expect(read.calls).toHaveLength(0);
    expect(screen.queryByText('Painting')).toBeNull();
  });
});
