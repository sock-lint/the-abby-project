import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, userEvent, waitFor, within } from '../../../test/render';
import { server } from '../../../test/server';
import Companions from './Companions';
import Mounts from './Mounts';

vi.mock('../../../components/companion/CompanionPreview', () => ({ default: ({ creature, children }) => <section aria-label="Companion home"><p>{creature.species.name}</p>{children}</section> }));
const chick = { id: 11, catalog_available: true, species: { id: 1, name: 'Chick', slug: 'chick', sprite_key: 'cute-chick', icon: '🐤' }, potion: { id: 1, name: 'Base', slug: 'base', rarity: 'common' }, growth_points: 30, is_active: false };
const savedCat = { id: 12, catalog_available: false, species: { id: 2, name: 'Cat', sprite_key: 'cat', icon: '🐱' }, potion: { id: 1, name: 'Base', slug: 'base', rarity: 'common' }, growth_points: 25, is_active: true };

beforeEach(() => {
  window.localStorage.clear();
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json({ id: 1, role: 'child', username: 'synthetic-review' })));
});

describe('saved pet collection', () => {
  it('keeps a supported companion at home, separates counts and still feeds an earlier owned pet', async () => {
    const user = userEvent.setup();
    const feed = vi.fn(() => HttpResponse.json({ growth_added: 5, new_growth: 30 }));
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [savedCat, chick], mounts: [], total_possible: 1 })),
      http.get('*/api/inventory/', () => HttpResponse.json([{ id: 1, quantity: 2, item: { id: 7, name: 'Earlier food', item_type: 'food', icon: '🍎', catalog_available: false } }])),
      http.post('*/api/pets/12/feed/', feed),
    );
    renderWithProviders(<Companions />);
    const home = await screen.findByRole('region', { name: 'Companion home' });
    expect(within(home).getByText('Chick')).toBeInTheDocument();
    expect(within(home).queryByText('Cat')).toBeNull();
    expect(screen.getByText('1 of 1')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Saved collection' })).getByRole('button', { name: 'Care for Base Cat' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Care for Base Cat' }));
    await user.click(screen.getByRole('button', { name: /Earlier food/ }));
    await waitFor(() => expect(feed).toHaveBeenCalled());
  });

  it('keeps saved expedition claims usable and does not advertise riding or unsupported breeding', async () => {
    const user = userEvent.setup();
    const claim = vi.fn(() => HttpResponse.json({ expedition_id: 50, coins_awarded: 0, items: [], freshly_claimed: false, mount: { species_name: 'Cat' } }));
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], total_possible: 1, mounts: [
        { ...chick, evolved_to_mount: undefined, can_breed: false, is_active: false },
        { ...savedCat, can_breed: false, active_expedition: { id: 50, status: 'active', is_ready: true } },
      ] })),
      http.post('*/api/expeditions/50/claim/', claim),
    );
    renderWithProviders(<Mounts />);
    expect(await screen.findByRole('region', { name: 'Saved collection' })).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: 'Companion home' })).getByText('Chick')).toBeInTheDocument();
    expect(screen.queryByText('riding')).toBeNull();
    expect(screen.queryByText('ready to breed')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Claim expedition rewards for Cat' }));
    await waitFor(() => expect(claim).toHaveBeenCalled());
  });
});
