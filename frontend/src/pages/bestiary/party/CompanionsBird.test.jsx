import { describe, expect, it, vi } from 'vitest';
import { HttpResponse, http } from 'msw';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server } from '../../../test/server';
import { AuthProvider } from '../../../hooks/useApi';
import { buildUser } from '../../../test/factories';
import Companions from './Companions';

const preview = vi.hoisted(() => ({ props: null }));
vi.mock('../../../components/companion/CompanionPreview', () => ({ default: (props) => {
  preview.props = props;
  return <section aria-label="Companion home"><p>{props.creature.evolution_stage}</p>{props.children}</section>;
} }));
vi.mock('../PetCeremonyModal', () => ({ default: () => <div role="dialog">Legacy evolution celebration</div> }));

const pet = {
  id: 1, name: 'Peep', species: { id: 42, slug: 'chick', name: 'Chick', sprite_key: 'cute-chick', icon: 'C' },
  potion: { id: 41, slug: 'base', name: 'Base', rarity: 'common' }, catalog_available: true,
  is_active: true, growth_points: 35, evolved_to_mount: false, evolution_stage: 'chick',
};
const food = [{ item: { id: 100, item_type: 'food', name: 'Birdseed' }, quantity: 2 }];

function page() { return render(<MemoryRouter><AuthProvider><Companions /></AuthProvider></MemoryRouter>); }

describe('Server-confirmed Bird growth in Companions', () => {
  it.each([
    ['chick', 'fledgling', 50, false],
    ['fledgling', 'bird', 100, true],
  ])('waits for the saved %s → %s stage, retains it after remount, and sends only the existing feed request', async (from, to, growth, evolved) => {
    Element.prototype.scrollIntoView = vi.fn();
    const user = userEvent.setup();
    let current = { ...pet, evolution_stage: from, growth_points: growth - 15 };
    let releaseRead;
    let heldRead = null;
    const requests = [];
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/pets/stable/', async () => {
        if (heldRead) await heldRead;
        return HttpResponse.json({ pets: [current], mounts: [], total_possible: 1 });
      }),
      http.get('*/api/inventory/', () => HttpResponse.json(food)),
      http.post('*/api/pets/1/feed/', async ({ request }) => {
        requests.push({ method: request.method, body: await request.json() });
        current = { ...current, growth_points: growth, evolution_stage: to, evolved_to_mount: evolved };
        heldRead = new Promise((resolve) => { releaseRead = resolve; });
        return HttpResponse.json({ new_growth: growth, growth_added: 15, evolved, evolution_stage: to });
      }),
    );
    const view = page();
    await user.click(await screen.findByRole('button', { name: 'Feed your companion' }));
    // A ready shared scene displays the supplied Evolve take; 2D retains its ceremony.
    act(() => preview.props.onPresentationChange({ creatureId: 1, sharedBirdReady: true, evolutionMotionEnabled: true }));
    await user.click(within(screen.getByRole('dialog', { name: 'Care for Peep' })).getByRole('button', { name: /Birdseed/ }));
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(within(screen.getByRole('region', { name: 'Companion home' })).getByText(from)).toBeInTheDocument();
    expect(screen.queryByText('Legacy evolution celebration')).toBeNull();
    await act(async () => { heldRead = null; releaseRead(); });
    await waitFor(() => expect(preview.props.creature.evolution_stage).toBe(to));
    expect(preview.props.reaction).toBeNull();
    view.unmount();
    const restored = page();
    await waitFor(() => expect(within(screen.getByRole('region', { name: 'Companion home' })).getByText(to)).toBeInTheDocument());
    expect(requests).toEqual([{ method: 'POST', body: { food_item_id: 100 } }]);
    restored.unmount();
  });
});
