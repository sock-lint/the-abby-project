import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../../hooks/useApi';
import { buildUser } from '../../test/factories';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import Hatchery from './hatchery/Hatchery';
import Mounts from './party/Mounts';
import PetCeremonyModal from './PetCeremonyModal';

vi.mock('../../components/companion/CompanionPreview', () => ({
  default: ({ children }) => <section aria-label="Companion home">{children}</section>,
}));
vi.mock('../../pedestal/PedestalPreview', () => ({ default: () => null }));

const potion = { id: 41, slug: 'base', name: 'Base', rarity: 'common' };
const mounts = [
  { id: 1, species: { id: 42, slug: 'chick', name: 'Chick', sprite_key: 'cute-chick', icon: '🐥' }, potion, catalog_available: true, can_breed: true, last_bred_at: null, expedition_available: true },
  { id: 2, species: { id: 43, slug: 'meshtint-bat', name: 'Bat', sprite_key: 'meshtint-bat', icon: '🦇' }, potion, catalog_available: true, can_breed: true, last_bred_at: new Date().toISOString(), expedition_available: true },
];

describe('Pets without breeding', () => {
  it.each([
    ['Hatchery', Hatchery],
    ['Grown pets', Mounts],
  ])('keeps %s focused on pets when an older response includes breeding eligibility', async (heading, Page) => {
    const breed = spyHandler('post', /\/api\/mounts\/breed\/$/, {});
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts, breeding_available: true, total_possible: 15 })),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      breed.handler,
    );
    render(<MemoryRouter><AuthProvider><Page /></AuthProvider></MemoryRouter>);
    await screen.findByRole('heading', { name: heading, exact: true });
    expect(screen.queryAllByText(/breed|pairing|cooldown|Cosmic potion/i)).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /breed/i })).toBeNull();
    expect(screen.queryByRole('combobox', { name: /grown pet/i })).toBeNull();
    expect(breed.calls).toHaveLength(0);
  });

  it('does not render a celebration for a retired breeding mode', () => {
    render(<PetCeremonyModal mode="breed" parents={mounts} result={{ egg_item_name: 'Chick Egg' }} reducedMotion onDismiss={() => {}} />);
    expect(screen.queryByRole('alertdialog')).toBeNull();
  });
});
