import { afterEach, describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { renderWithProviders } from '../test/render';
import { server } from '../test/server';
import { emptyPulse } from '../test/pulseFixtures';
import VitalPipStrip from '../components/dashboard/VitalPipStrip';
import ExpeditionToastStack from '../components/ExpeditionToastStack';
import CompanionGrowthToastStack from '../components/CompanionGrowthToastStack';
import Companions from '../pages/bestiary/party/Companions';
import OwnedMountGrid from '../pages/bestiary/party/OwnedMountGrid';
import ExpeditionLaunchSheet from '../pages/bestiary/party/ExpeditionLaunchSheet';
import SpeciesDetailSheet from '../pages/bestiary/codex/SpeciesDetailSheet';
import PetCeremonyModal from '../pages/bestiary/PetCeremonyModal';

// Synthetic names exercise a future family without enabling production offers
// or inventing accepted artwork. Existing Bird names remain in the registry.
vi.mock('../../../shared/catalog/companion-lifecycle.json', async (importOriginal) => {
  const { default: catalog } = await importOriginal();
  return { default: { ...catalog, family_forms: [...catalog.family_forms, {
    species_slug: 'test-fox', sprite_key: 'test-fox', potion_slugs: ['base'],
    names: { egg: 'Fox Egg', baby: 'Kit', middle: 'Young fox', grown: 'Forest fox' },
  }] } };
});

const pet = {
  id: 81, species: { id: 82, slug: 'test-fox', name: 'Fox family', sprite_key: 'test-fox', icon: '🦊' },
  potion: { id: 83, slug: 'base', name: 'Base', rarity: 'common' },
  lifecycle_stage: 'middle', growth_points: 65, evolved_to_mount: false,
  happiness_level: 'happy', is_active: true, catalog_available: true,
};
const mount = { ...pet, id: 84, lifecycle_stage: 'grown', evolved_to_mount: true, can_breed: false };

afterEach(() => vi.unstubAllEnvs());

describe('Registered family form names across the application', () => {
  it('uses the middle form consistently in Today, the companion home, and care', async () => {
    vi.stubEnv('VITE_COMPANION_3D', 'false');
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [pet], mounts: [], total_possible: 1 })),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    renderWithProviders(<><VitalPipStrip activePet={pet} /><Companions /></>);
    expect(screen.getByRole('button', { name: 'Young fox growth' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Base Young fox' })).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole('button', { name: 'Feed your companion' }));
    const care = screen.getByRole('dialog', { name: 'Care for Base Young fox' });
    expect(within(care).getByText('Young fox · 65/100 growth')).toBeInTheDocument();
  });

  it('uses the grown form in catalog, expedition launch and collection actions', () => {
    renderWithProviders(<>
      <SpeciesDetailSheet species={{ ...pet.species, discovered: true, available_potions: [pet.potion] }} onClose={() => {}} />
      <ExpeditionLaunchSheet mount={mount} />
      <OwnedMountGrid mounts={[mount]} />
    </>);
    expect(screen.getByRole('img', { name: 'Base Forest fox — not yet evolved' })).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: 'Send Forest fox on an expedition' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send Forest fox on an expedition' })).toBeInTheDocument();
  });

  it('names the confirmed middle and grown forms in passive growth and expedition notices', async () => {
    const identity = { species_name: pet.species.name, species_slug: pet.species.slug,
      species_sprite_key: pet.species.sprite_key, species_icon: pet.species.icon,
      potion_slug: pet.potion.slug, potion_name: pet.potion.name };
    renderWithProviders(<><CompanionGrowthToastStack /><ExpeditionToastStack /></>, {
      withAuth: false,
      pulse: emptyPulse({
        companion_growth: { events: [{ ...identity, pet_id: pet.id, growth_added: 2, new_growth: 65, lifecycle_stage: 'middle', evolved: false }] },
        expeditions_ready: [{ ...identity, id: 85, tier: 'short' }],
      }),
    });
    expect(await screen.findByText('Base Young fox grew')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Forest fox returned — claim rewards on Grown pets' })).toBeInTheDocument();
  });

  it('reveals the registered baby form when hatching while retaining its own artwork fallback', () => {
    renderWithProviders(<PetCeremonyModal mode="hatch" pet={{ ...pet, lifecycle_stage: 'baby', growth_points: 0 }} reducedMotion onDismiss={() => {}} />);
    expect(screen.getByRole('heading', { name: 'Base Kit' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Kit' })).toHaveTextContent('🦊');
    expect(screen.queryByText(/Chick|Fledgling|Bird/)).toBeNull();
  });

  it('names the registered grown form when evolution is confirmed', () => {
    renderWithProviders(<PetCeremonyModal mode="evolve" species={pet.species} potion={pet.potion} reducedMotion onDismiss={() => {}} />);
    expect(screen.getByRole('heading', { name: 'Base Forest fox' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Forest fox' })).toHaveTextContent('🦊');
  });
});
