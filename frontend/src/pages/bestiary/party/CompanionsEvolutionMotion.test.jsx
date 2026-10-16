import { useEffect } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HttpResponse, http } from 'msw';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { server } from '../../../test/server';
import { AuthProvider } from '../../../hooks/useApi';
import { buildUser } from '../../../test/factories';
import Companions from './Companions';

const scene = vi.hoisted(() => ({ props: null }));
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});
// Keep the real Preview, its View checkbox and the real ceremony. Only the
// optional renderer/art boundary is synthetic; readiness alone is not motion.
vi.mock('../../../companion/appearance', () => ({
  creatureLabel: () => 'Base Chick',
  resolveAppearance: (creature) => ({ key: creature.evolution_stage, pipeline: 'abby-assets-bird', url: `/${creature.evolution_stage}.glb` }),
}));
vi.mock('../../../companion/CompanionScene', () => ({ default: function SyntheticScene(props) {
  scene.props = props;
  const { onReady } = props;
  useEffect(() => { onReady(); }, [onReady]);
  return <span data-testid="evolution-scene" />;
} }));

const pet = {
  id: 1, name: 'Peep', species: { id: 42, slug: 'chick', name: 'Chick', sprite_key: 'cute-chick', icon: 'C' },
  potion: { id: 41, slug: 'base', name: 'Base', rarity: 'common' }, catalog_available: true,
  is_active: true, growth_points: 85, evolved_to_mount: false, evolution_stage: 'fledgling',
};

afterEach(() => vi.restoreAllMocks());

describe('Evolution feedback with real companion display preferences', () => {
  it.each(['disabled', 'reduced', 'enabled'])('preserves the evolution moment when motion is %s', async (mode) => {
    Element.prototype.scrollIntoView = vi.fn();
    let reduced = false;
    const listeners = new Set();
    const media = { get matches() { return reduced; },
      addEventListener: (_event, listener) => listeners.add(listener),
      removeEventListener: (_event, listener) => listeners.delete(listener),
    };
    vi.spyOn(window, 'matchMedia').mockReturnValue(media);
    const user = userEvent.setup();
    const requests = [];
    let current = pet;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [current], mounts: [], total_possible: 1 })),
      http.get('*/api/inventory/', () => HttpResponse.json([{ item: { id: 100, item_type: 'food', name: 'Birdseed' }, quantity: 1 }])),
      http.post('*/api/pets/1/feed/', async ({ request }) => {
        requests.push({ method: request.method, body: await request.json() });
        current = { ...pet, growth_points: 100, evolved_to_mount: true, evolution_stage: 'bird' };
        return HttpResponse.json({ new_growth: 100, growth_added: 15, evolved: true, evolution_stage: 'bird' });
      }),
    );
    render(<MemoryRouter><AuthProvider><Companions /></AuthProvider></MemoryRouter>);
    await screen.findByTestId('evolution-scene');
    await waitFor(() => expect(screen.queryByText('Loading the woodland…')).toBeNull());
    await user.click(screen.getByText('View'));
    if (mode === 'disabled') {
      await user.click(screen.getByRole('checkbox', { name: 'Animate companion' }));
      expect(scene.props.animate).toBe(false);
    } else if (mode === 'reduced') {
      act(() => { reduced = true; listeners.forEach((listener) => listener({ matches: true })); });
      expect(window.matchMedia('(prefers-reduced-motion: reduce)').matches).toBe(true);
      // A device preference change must work without toggling the view setting.
      expect(screen.getByRole('checkbox', { name: 'Animate companion' })).toBeChecked();
    }
    await user.click(screen.getByText('View'));
    await user.click(screen.getByRole('button', { name: 'Feed your companion' }));
    await user.click(within(screen.getByRole('dialog', { name: 'Care for Peep' })).getByRole('button', { name: /Birdseed/ }));
    await waitFor(() => expect(requests).toHaveLength(1));
    await waitFor(() => expect(scene.props.appearance.key).toBe('bird'));
    if (mode === 'enabled') {
      expect(screen.queryByRole('alertdialog')).toBeNull();
      expect(scene.props.evolution).toMatchObject({ from: 'fledgling', to: 'bird' });
    } else {
      const ceremony = await screen.findByRole('alertdialog', { name: 'Base Chick' });
      expect(within(ceremony).getByText('evolution complete')).toBeInTheDocument();
      expect(within(ceremony).getByText('is ready to explore.')).toBeInTheDocument();
      expect(ceremony.querySelector('.animate-gilded-glint, .animate-cosmic-burst')).toBeNull();
    }
    expect(requests).toEqual([{ method: 'POST', body: { food_item_id: 100 } }]);
  });
});
