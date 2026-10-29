import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor, within, act } from '../../test/render';
import { server } from '../../test/server';
import { buildParent, buildUser } from '../../test/factories';
import { buildEggDiscovery, buildEggEnvelope, buildEggOffer, rareRequirements } from '../../test/eggDiscoveries';
import { SpaceContext } from '../../providers/spaceContext';
import { useAuth } from '../../hooks/useApi';
import EggDiscoveryPanel from './EggDiscoveryPanel';

function setup(initial = buildEggEnvelope(), account = buildUser({ family: { id: 1 } })) {
  let envelope = initial;
  const requests = [];
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(account)),
    http.get('*/api/egg-discoveries/', ({ request }) => { requests.push(request); return HttpResponse.json(envelope); }),
  );
  return { requests, set: (next) => { envelope = next; } };
}

describe('Egg discovery preview', () => {
  it('keeps other eggs behind a deliberate switch and saves the previous discovery when choosing one', async () => {
    const active = buildEggDiscovery();
    const other = buildEggOffer({ key: 'bee-base', name: 'Bee Egg' });
    const state = setup(buildEggEnvelope({ active_id: active.id, discoveries: [active], offers: [buildEggOffer(), other] }));
    const selections = [];
    server.use(http.post('*/api/egg-discoveries/select/', async ({ request }) => {
      selections.push(await request.json());
      const next = buildEggEnvelope({ active_id: 2, discoveries: [{ ...active, status: 'paused', can_resume: true }, buildEggDiscovery({ id: 2, offer_key: other.key, key: other.key, name: other.name })], offers: [other] });
      state.set(next);
      return HttpResponse.json(next);
    }));
    const { user } = renderWithProviders(<EggDiscoveryPanel />);
    await screen.findByRole('region', { name: 'Your active egg discovery' });
    expect(screen.getByRole('button', { name: 'Choose Bee Egg' })).not.toBeVisible();
    await user.click(screen.getByText('Choose another egg'));
    await user.click(screen.getByRole('button', { name: 'Choose Bee Egg' }));
    await waitFor(() => expect(screen.getByRole('region', { name: 'Your active egg discovery' })).toHaveTextContent('Bee Egg'));
    expect(screen.getByRole('region', { name: 'Paused egg discoveries' })).toHaveTextContent('60 of 240 minutes recorded');
    expect(selections).toEqual([{ offer_key: 'bee-base', client_request_id: expect.any(String) }]);
  });

  it('stays hidden when disabled and makes no discovery requests in parent Family space', async () => {
    const state = setup({ enabled: false, offers: [], discoveries: [], active_id: null });
    const first = renderWithProviders(<EggDiscoveryPanel />);
    await waitFor(() => expect(state.requests).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
    expect(screen.queryByText('Egg discoveries')).toBeNull();
    first.unmount();
    const family = setup(buildEggEnvelope(), buildParent());
    renderWithProviders(<EggDiscoveryPanel />);
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull());
    expect(screen.queryByText('Egg discoveries')).toBeNull();
    expect(state.requests).toHaveLength(1);
    expect(family.requests).toHaveLength(0);
  });

  it('lets a personal parent choose their own egg using the personal request scope', async () => {
    const state = setup(buildEggEnvelope(), buildParent());
    let mutation;
    server.use(http.post('*/api/egg-discoveries/select/', async ({ request }) => {
      mutation = { body: await request.json(), space: request.headers.get('X-Abby-Space') };
      const next = buildEggEnvelope({ active_id: 1, discoveries: [buildEggDiscovery()] });
      state.set(next);
      return HttpResponse.json(next);
    }));
    const { user } = renderWithProviders(<SpaceContext.Provider value={{ space: 'personal', isFamilySpace: false, isPersonalSpace: true, isParentAccount: true }}><EggDiscoveryPanel /></SpaceContext.Provider>);
    await user.click(await screen.findByRole('button', { name: 'Choose Wolf Egg' }));
    expect(await screen.findByRole('region', { name: 'Your active egg discovery' })).toBeInTheDocument();
    expect(mutation.space).toBe('personal');
    expect(mutation.body).toEqual({ offer_key: 'wolf-base', client_request_id: expect.any(String) });
    expect(state.requests.every((request) => request.headers.get('X-Abby-Space') === 'personal')).toBe(true);
  });

  it('chooses, pauses, and resumes the same discovery with saved activity', async () => {
    const state = setup();
    let stored = buildEggDiscovery();
    const selections = [];
    const pauses = [];
    server.use(
      http.post('*/api/egg-discoveries/select/', async ({ request }) => {
        selections.push(await request.json());
        stored = { ...stored, status: 'active', can_resume: false };
        const next = buildEggEnvelope({ discoveries: [stored], active_id: stored.id });
        state.set(next); return HttpResponse.json(next);
      }),
      http.post('*/api/egg-discoveries/1/pause/', async ({ request }) => {
        pauses.push(await request.json());
        stored = { ...stored, status: 'paused', can_resume: true };
        const next = buildEggEnvelope({ discoveries: [stored] });
        state.set(next); return HttpResponse.json(next);
      }),
    );
    const { user } = renderWithProviders(<EggDiscoveryPanel />);
    expect(await screen.findByText(/240 minutes total/)).toHaveTextContent('90 minutes in each of 2 activity types');
    await user.click(screen.getByRole('button', { name: 'Choose Wolf Egg' }));
    expect(await screen.findByText('60 of 240 minutes recorded')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Pause discovery' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Pause discovery' }));
    const paused = await screen.findByRole('region', { name: 'Paused egg discoveries' });
    expect(within(paused).getByText('60 of 240 minutes recorded')).toBeInTheDocument();
    await waitFor(() => expect(within(paused).getByRole('button', { name: 'Resume Wolf Egg' })).toBeEnabled());
    await user.click(within(paused).getByRole('button', { name: 'Resume Wolf Egg' }));
    expect(await screen.findByRole('region', { name: 'Your active egg discovery' })).toHaveTextContent('60 of 240 minutes recorded');
    expect(selections).toHaveLength(2);
    expect(selections[1].client_request_id).not.toBe(selections[0].client_request_id);
    expect(pauses[0]).toEqual({ client_request_id: expect.any(String) });
  });

  it('renders server search results, chance, and guarantee without a search or claim button', async () => {
    setup(buildEggEnvelope({ discoveries: [buildEggDiscovery({ tier: 'rare', requirements: rareRequirements,
      minutes: { reading: 15, movement: 0, practice: 10 }, searches: [{ number: 1, found: false, guaranteed: false }, { number: 2, found: false, guaranteed: false }], remaining_searches: 3 })], active_id: 1 }));
    renderWithProviders(<EggDiscoveryPanel />);
    const active = await screen.findByRole('region', { name: 'Your active egg discovery' });
    expect(active).toHaveTextContent('Each search uses 60 minutes of activity, with at most 30 minutes from one activity type');
    expect(active).toHaveTextContent('20% chance on each of the first 4 searches');
    expect(active).toHaveTextContent('Search 5 guarantees this egg');
    expect(active).toHaveTextContent('All 5 searches together use 300 minutes of varied activity');
    expect(active).toHaveTextContent('At most 3 more searches');
    expect(within(active).getByRole('list', { name: 'Saved search results' }).children).toHaveLength(2);
    expect(within(active).getByText('15 minutes')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /search|claim|roll/i })).toBeNull();
    expect(screen.queryByRole('region', { name: /artwork preview/i })).toBeNull();
    expect(document.querySelector('img[src*="wolf"]')).toBeNull();
  });

  it('preserves the exact UUID and intent when selection response is uncertain', async () => {
    const state = setup();
    const calls = [];
    server.use(http.post('*/api/egg-discoveries/select/', async ({ request }) => {
      calls.push(await request.json());
      if (calls.length === 1) return HttpResponse.error();
      const next = buildEggEnvelope({ discoveries: [buildEggDiscovery()], active_id: 1 });
      state.set(next); return HttpResponse.json(next);
    }));
    const { user } = renderWithProviders(<EggDiscoveryPanel />);
    await user.click(await screen.findByRole('button', { name: 'Choose Wolf Egg' }));
    const retry = await screen.findByRole('button', { name: 'Retry change' });
    expect(calls).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Choose Wolf Egg' })).toBeDisabled();
    await user.click(retry);
    expect(await screen.findByRole('region', { name: 'Your active egg discovery' })).toBeInTheDocument();
    expect(calls).toHaveLength(2);
    expect(calls[1]).toEqual(calls[0]);
  });

  it.each([1, 2, 3, 4])('shows a saved early discovery on search %i without inventing a guarantee', async (number) => {
    setup(buildEggEnvelope({ discoveries: [buildEggDiscovery({ status: 'completed', tier: 'rare', requirements: rareRequirements, remaining_searches: 0,
      searches: Array.from({ length: number }, (_, i) => ({ number: i + 1, found: i === number - 1, guaranteed: false })) })] }));
    renderWithProviders(<EggDiscoveryPanel />);
    const earned = await screen.findByRole('region', { name: 'Earned Wolf Egg' });
    expect(earned).toHaveTextContent(`Search ${number}: Egg found`);
    expect(earned).not.toHaveTextContent('guaranteed discovery');
    expect(screen.queryByRole('button', { name: /claim/i })).toBeNull();
  });

  it('keeps a winning result pending until an explicit delivery retry returns its supplies', async () => {
    const pending = buildEggDiscovery({ tier: 'rare', requirements: rareRequirements, delivery_pending: true, remaining_searches: 0,
      minutes: { reading: 30, movement: 0, practice: 30 }, searches: [{ number: 1, found: true, guaranteed: false }] });
    const state = setup(buildEggEnvelope({ discoveries: [{ ...pending, delivery_pending: false, searches: [], remaining_searches: 5,
      minutes: { reading: 30, movement: 0, practice: 0 } }], active_id: pending.id }));
    const calls = [];
    const activities = [];
    server.use(http.post('*/api/egg-discoveries/practice/', async ({ request }) => {
      activities.push(await request.json());
      const next = buildEggEnvelope({ discoveries: [pending], active_id: pending.id });
      state.set(next); return HttpResponse.json(next);
    }), http.post('*/api/egg-discoveries/select/', async ({ request }) => {
      calls.push(await request.json());
      if (calls.length === 1) return HttpResponse.json(buildEggEnvelope({ discoveries: [pending], active_id: pending.id }));
      const delivered = { ...pending, status: 'completed', delivery_pending: false,
        receipt: { items: [{ item_id: 71, item_name: 'Wolf Egg', item_type: 'egg', quantity: 1 }] } };
      const next = buildEggEnvelope({ discoveries: [delivered] });
      state.set(next); return HttpResponse.json(next);
    }));
    const { user } = renderWithProviders(<EggDiscoveryPanel />);
    await user.click(await screen.findByRole('button', { name: 'Log making or practice' }));
    const activityForm = await screen.findByRole('dialog', { name: 'Log making or practice' });
    await user.type(within(activityForm).getByLabelText('What did you make or practice?'), 'Drawing');
    await user.type(within(activityForm).getByLabelText('Minutes'), '30');
    await user.click(within(activityForm).getByRole('button', { name: 'Save activity' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    const active = screen.getByRole('region', { name: 'Your active egg discovery' });
    expect(active).toHaveTextContent('Activity saved. Your discovery is complete, but its egg and supplies have not been delivered yet.');
    expect(active).toHaveTextContent('Search 1: Discovery complete — delivery pending');
    expect(active).not.toHaveTextContent('Egg earned');
    expect(active).not.toHaveTextContent('Egg found');
    expect(active).not.toHaveTextContent('At most 0 more searches');
    expect(screen.queryByRole('link', { name: 'Take your egg to the Hatchery' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Log making or practice' })).toBeNull();
    const retry = within(active).getByRole('button', { name: 'Try delivery again' });
    await waitFor(() => expect(retry).toBeEnabled());
    const previousReads = state.requests.length;
    await act(async () => window.dispatchEvent(new Event('abby:egg-discoveries-changed')));
    await waitFor(() => expect(state.requests).toHaveLength(previousReads + 1));
    expect(calls).toEqual([]);
    expect(activities).toHaveLength(1);
    await waitFor(() => expect(retry).toBeEnabled());
    await user.click(retry);
    await waitFor(() => expect(calls).toHaveLength(1));
    await waitFor(() => expect(retry).toBeEnabled());
    expect(active).toHaveTextContent('No more activity is needed for this egg. Your result stays saved.');
    await user.click(retry);
    const earned = await screen.findByRole('region', { name: 'Earned Wolf Egg' });
    expect(earned).toHaveTextContent('Egg earned');
    expect(earned).toHaveTextContent('Wolf Egg × 1');
    expect(within(earned).getByRole('link', { name: 'Take your egg to the Hatchery' })).toBeInTheDocument();
    expect(calls).toEqual([{ offer_key: pending.offer_key, client_request_id: expect.any(String) }, { offer_key: pending.offer_key, client_request_id: expect.any(String) }]);
    expect(calls[1].client_request_id).not.toBe(calls[0].client_request_id);
    expect(calls[0].client_request_id).not.toBe(activities[0].client_request_id);
  });

  it('offers an explicit delivery retry for a paused completed discovery', async () => {
    setup(buildEggEnvelope({ discoveries: [buildEggDiscovery({ status: 'paused', can_resume: true, delivery_pending: true,
      minutes: { reading: 90, movement: 0, practice: 150 } })] }));
    renderWithProviders(<EggDiscoveryPanel />);
    const paused = await screen.findByRole('region', { name: 'Paused egg discoveries' });
    expect(within(paused).getByRole('button', { name: 'Try delivery again' })).toBeEnabled();
    expect(paused).toHaveTextContent('No more activity is needed for this egg. Your result stays saved.');
    expect(screen.queryByRole('button', { name: 'Resume Wolf Egg' })).toBeNull();
  });

  it('logs practice with minutes only once across uncertain retries and shows guaranteed supplies', async () => {
    const state = setup(buildEggEnvelope({ discoveries: [buildEggDiscovery({ tier: 'rare', requirements: rareRequirements, remaining_searches: 1,
      searches: Array.from({ length: 4 }, (_, i) => ({ number: i + 1, found: false, guaranteed: false })) })], active_id: 1 }));
    const calls = [];
    server.use(http.post('*/api/egg-discoveries/practice/', async ({ request }) => {
      calls.push(await request.json());
      if (calls.length === 1) return HttpResponse.error();
      const completed = buildEggDiscovery({ tier: 'rare', requirements: rareRequirements, status: 'completed', remaining_searches: 0,
        searches: [...Array.from({ length: 4 }, (_, i) => ({ number: i + 1, found: false, guaranteed: false })), { number: 5, found: true, guaranteed: true }],
        receipt: { items: [{ item_id: 71, item_name: 'Wolf Egg', item_type: 'egg', quantity: 1 }, { item_id: 80, item_name: 'Base Potion', item_type: 'potion', quantity: 1 }] } });
      const next = buildEggEnvelope({ discoveries: [completed] });
      state.set(next); return HttpResponse.json(next);
    }));
    const { user } = renderWithProviders(<EggDiscoveryPanel />);
    await user.click(await screen.findByRole('button', { name: 'Log making or practice' }));
    const dialog = await screen.findByRole('dialog', { name: 'Log making or practice' });
    await user.type(within(dialog).getByLabelText('What did you make or practice?'), 'Drawing');
    await user.type(within(dialog).getByLabelText('Minutes'), '30');
    await user.click(within(dialog).getByRole('button', { name: 'Save activity' }));
    await within(dialog).findByText(/could not confirm this save/);
    expect(within(dialog).getByLabelText('Minutes')).toBeDisabled();
    expect(calls).toHaveLength(1);
    await user.click(within(dialog).getByRole('button', { name: 'Retry save' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(calls[0]).toMatchObject({ name: 'Drawing', minutes: 30 });
    expect(calls[1]).toEqual(calls[0]);
    const earned = screen.getByRole('region', { name: 'Earned Wolf Egg' });
    expect(earned).toHaveTextContent('Search 5: Egg found — guaranteed discovery');
    expect(earned).toHaveTextContent('Wolf Egg × 1');
    expect(within(earned).getByRole('link', { name: 'Take your egg to the Hatchery' })).toHaveAttribute('href', '/bestiary?tab=hatchery');
  });

  it('shows inline practice validation and makes a new request for corrected input', async () => {
    setup(buildEggEnvelope({ discoveries: [buildEggDiscovery()], active_id: 1 }));
    const calls = [];
    server.use(http.post('*/api/egg-discoveries/practice/', async ({ request }) => {
      calls.push(await request.json());
      return HttpResponse.json({ name: ['Choose an activity name.'] }, { status: 400 });
    }));
    const { user } = renderWithProviders(<EggDiscoveryPanel />);
    await user.click(await screen.findByRole('button', { name: 'Log making or practice' }));
    await user.type(screen.getByLabelText('What did you make or practice?'), 'Drawing');
    await user.type(screen.getByLabelText('Minutes'), '20');
    await user.click(screen.getByRole('button', { name: 'Save activity' }));
    expect(await screen.findByText('Choose an activity name.')).toBeInTheDocument();
    await user.clear(screen.getByLabelText('What did you make or practice?'));
    await user.type(screen.getByLabelText('What did you make or practice?'), 'Music');
    await user.click(screen.getByRole('button', { name: 'Save activity' }));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1].client_request_id).not.toBe(calls[0].client_request_id);
  });

  it('resumes accepted seasonal work outside its new-offer window', async () => {
    const season = { starts_on: '2026-10-01', ends_on: '2026-10-31' };
    const saved = buildEggDiscovery({ status: 'paused', can_resume: true, season });
    setup(buildEggEnvelope({ discoveries: [saved], offers: [buildEggOffer({ season, eligible: false, unavailable_reason: 'season_closed' })] }));
    renderWithProviders(<EggDiscoveryPanel />);
    expect(await screen.findByRole('button', { name: 'Resume Wolf Egg' })).toBeEnabled();
    expect(screen.getByText('Seasonal discovery saved. You can finish after the season ends.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Choose Wolf Egg' })).toBeNull();
  });

  it('keeps unavailable offers disabled and allows retrying a failed read', async () => {
    let fail = true;
    setup();
    server.use(http.get('*/api/egg-discoveries/', () => fail ? HttpResponse.json({ error: 'Temporarily unavailable.' }, { status: 503 })
      : HttpResponse.json(buildEggEnvelope({ offers: [buildEggOffer({ eligible: false, unavailable_reason: 'already_owned' })] }))));
    const { user } = renderWithProviders(<EggDiscoveryPanel />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Temporarily unavailable.');
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('button', { name: 'Choose Wolf Egg' })).toBeDisabled();
    expect(screen.getByText('You already have this appearance.')).toBeInTheDocument();
  });

  it('drops a delayed mutation after the account changes', async () => {
    setup();
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    let received = false;
    server.use(http.post('*/api/egg-discoveries/select/', async () => {
      received = true; await held;
      return HttpResponse.json(buildEggEnvelope({ discoveries: [buildEggDiscovery({ name: 'Previous account private egg' })], active_id: 1 }));
    }));
    function Switcher() {
      const { setUser } = useAuth();
      return <ButtonSwitcher onClick={() => setUser(buildUser({ id: 2, family: { id: 2 } }))} />;
    }
    function ButtonSwitcher({ onClick }) { return <button onClick={onClick}>Switch account</button>; }
    const { user } = renderWithProviders(<><EggDiscoveryPanel /><Switcher /></>);
    await user.click(await screen.findByRole('button', { name: 'Choose Wolf Egg' }));
    await waitFor(() => expect(received).toBe(true));
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    await screen.findByRole('button', { name: 'Choose Wolf Egg' });
    await act(async () => { release(); await held; });
    expect(screen.queryByText('Previous account private egg')).toBeNull();
    expect(screen.queryByRole('region', { name: 'Your active egg discovery' })).toBeNull();
  });
});
