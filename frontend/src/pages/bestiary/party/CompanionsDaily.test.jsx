import { beforeEach, describe, expect, it, vi } from 'vitest';
import { HttpResponse, http } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server } from '../../../test/server';
import { AuthProvider } from '../../../hooks/useApi';
import { buildUser } from '../../../test/factories';
import { spyHandler } from '../../../test/spy';
import Companions from './Companions';

const preview = vi.hoisted(() => ({ props: null }));
vi.mock('../../../components/companion/CompanionPreview', () => ({ default: (props) => {
  preview.props = props;
  return <section aria-label="Waiting companion">{props.children}</section>;
} }));
vi.mock('../PetCeremonyModal', () => ({ default: () => <div role="dialog">Confirmed expedition return</div> }));

const species = { id: 42, slug: 'chick', name: 'Chick', sprite_key: 'cute-chick', icon: 'C' };
const potion = { id: 41, slug: 'base', name: 'Base', rarity: 'common' };
const pet = { id: 1, species, potion, name: 'Peep', catalog_available: true, is_active: true, growth_points: 100, evolved_to_mount: true };
const mount = { id: 5, species, potion, catalog_available: true, can_breed: false, expedition_available: true, active_expedition: null };
const trip = { id: 33, status: 'active', is_ready: true, seconds_remaining: -5 };
const receipt = { expedition_id: 33, freshly_claimed: true, coins_awarded: 15, items: [], mount: { id: 5, species_name: 'Chick', potion_name: 'Base' } };
beforeEach(() => { preview.props = null; Element.prototype.scrollIntoView = vi.fn(); });

function page(handlers) {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())), ...handlers);
  return render(<MemoryRouter><AuthProvider><Companions /></AuthProvider></MemoryRouter>);
}
function stable(homeMount, homePet = pet) { return { pets: [homePet], mounts: homeMount ? [homeMount] : [], total_possible: 1 }; }

describe('Daily interactions from the companion home', () => {
  it('starts a grown Bird expedition directly from Companions with an explicit duration choice', async () => {
    const user = userEvent.setup();
    let current = mount;
    const start = spyHandler('post', /\/api\/mounts\/5\/expedition\/$/, () => {
      current = { ...mount, expedition_available: false, active_expedition: { ...trip, is_ready: false, seconds_remaining: 7200 } };
      return HttpResponse.json(current.active_expedition, { status: 201 });
    });
    page([
      http.get('*/api/pets/stable/', () => HttpResponse.json(stable(current))),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      start.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: 'Choose an expedition' }));
    expect(start.calls).toHaveLength(0);
    await user.click(await screen.findByRole('button', { name: /Short expedition/ }));
    expect(await screen.findByRole('heading', { name: 'Peep is exploring' })).toBeInTheDocument();
    expect(start.calls).toHaveLength(1);
    expect(start.calls[0]).toMatchObject({ method: 'POST', body: { tier: 'short' } });
    expect(new URL(start.calls[0].url).pathname).toBe('/api/mounts/5/expedition/');
    expect(preview.props.onInteract).toBeUndefined();
    expect(preview.props.reaction).toBeNull();
  });
  it('celebrates a fresh confirmed return then shows today’s completed adventure', async () => {
    const user = userEvent.setup();
    let current = { ...mount, expedition_available: false, active_expedition: trip };
    const claim = spyHandler('post', /\/api\/expeditions\/33\/claim\/$/, () => {
      current = { ...mount, expedition_available: false, expedition_available_at: '2026-10-13T00:00:00-07:00', expedition_available_in_seconds: 30000 };
      return receipt;
    });
    page([
      http.get('*/api/pets/stable/', () => HttpResponse.json(stable(current))),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      claim.handler,
    ]);
    await screen.findByRole('button', { name: 'Collect your finds' });
    expect(claim.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Collect your finds' }));
    expect(await screen.findByText('Confirmed expedition return')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'A good adventure today' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Choose an expedition' })).toBeNull();
    expect(claim.calls).toHaveLength(1);
    expect(claim.calls[0]).toMatchObject({ method: 'POST', body: null });
    expect(new URL(claim.calls[0].url).pathname).toBe('/api/expeditions/33/claim/');
    expect(preview.props.reaction).toMatchObject({ creatureId: 1, action: 'celebrate' });
  });
  it('refreshes a claim already collected elsewhere without showing another earned ceremony', async () => {
    const user = userEvent.setup();
    let current = { ...mount, expedition_available: false, active_expedition: trip };
    const claim = spyHandler('post', /\/api\/expeditions\/33\/claim\/$/, () => {
      current = { ...mount, expedition_available: false, expedition_available_in_seconds: 30000 };
      return { ...receipt, freshly_claimed: false, coins_awarded: 0 };
    });
    page([
      http.get('*/api/pets/stable/', () => HttpResponse.json(stable(current))),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      claim.handler,
    ]);
    await user.click(await screen.findByRole('button', { name: 'Collect your finds' }));
    await screen.findByRole('heading', { name: 'A good adventure today' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(preview.props.reaction).toBeNull();
    expect(claim.calls).toHaveLength(1);
    expect(claim.calls[0]).toMatchObject({ method: 'POST', body: null });
    expect(new URL(claim.calls[0].url).pathname).toBe('/api/expeditions/33/claim/');
  });
  it('does not celebrate a rejected food save', async () => {
    const user = userEvent.setup();
    page([
      http.get('*/api/pets/stable/', () => HttpResponse.json(stable(null, { ...pet, evolved_to_mount: false, growth_points: 30 }))),
      http.get('*/api/inventory/', () => HttpResponse.json([{ quantity: 1, item: { id: 100, item_type: 'food', name: 'Birdseed', icon: 'F' } }])),
      http.post('*/api/pets/1/feed/', () => HttpResponse.json({ error: 'That food was already used' }, { status: 400 })),
    ]);
    await user.click(await screen.findByRole('button', { name: 'Feed your companion' }));
    await user.click(await screen.findByRole('button', { name: /Birdseed/ }));
    await waitFor(() => expect(screen.getAllByRole('alert')[0]).toHaveTextContent('That food was already used'));
    expect(preview.props.reaction).toBeNull();
    expect(screen.getByRole('dialog', { name: 'Care for Peep' })).toBeInTheDocument();
  });
  it('reacts only after food consumption is confirmed by the server', async () => {
    const user = userEvent.setup();
    let finish;
    const response = new Promise((resolve) => { finish = resolve; });
    let saves = 0;
    page([
      http.get('*/api/pets/stable/', () => HttpResponse.json(stable(null, { ...pet, evolved_to_mount: false, growth_points: 30 }))),
      http.get('*/api/inventory/', () => HttpResponse.json([{ quantity: 1, item: { id: 100, item_type: 'food', name: 'Birdseed', icon: 'F' } }])),
      http.post('*/api/pets/1/feed/', async () => { saves += 1; await response; return HttpResponse.json({ new_growth: 45, growth_added: 15, evolved: false }); }),
    ]);
    await user.click(await screen.findByRole('button', { name: 'Feed your companion' }));
    await user.click(await screen.findByRole('button', { name: /Birdseed/ }));
    await waitFor(() => expect(saves).toBe(1));
    expect(preview.props.reaction).toBeNull();
    finish();
    await waitFor(() => expect(preview.props.reaction).toMatchObject({ creatureId: 1, action: 'celebrate' }));
    expect(screen.queryByRole('dialog', { name: 'Care for Peep' })).toBeNull();
  });
  it('ignores a delayed food receipt after credentials changed', async () => {
    const user = userEvent.setup();
    let finish;
    const response = new Promise((resolve) => { finish = resolve; });
    let reads = 0;
    let saves = 0;
    page([
      http.get('*/api/pets/stable/', () => { reads += 1; return HttpResponse.json(stable(null, { ...pet, evolved_to_mount: false, growth_points: 30 })); }),
      http.get('*/api/inventory/', () => HttpResponse.json([{ quantity: 1, item: { id: 100, item_type: 'food', name: 'Birdseed', icon: 'F' } }])),
      http.post('*/api/pets/1/feed/', async () => { saves += 1; await response; return HttpResponse.json({ new_growth: 45, growth_added: 15, evolved: false }); }),
    ]);
    await user.click(await screen.findByRole('button', { name: 'Feed your companion' }));
    await user.click(await screen.findByRole('button', { name: /Birdseed/ }));
    await waitFor(() => expect(saves).toBe(1));
    const initialReads = reads;
    localStorage.setItem('abby_auth_token', 'new-synthetic-account');
    finish();
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(preview.props.reaction).toBeNull();
    expect(reads).toBe(initialReads);
  });
});
