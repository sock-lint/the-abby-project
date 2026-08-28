import { describe, it, expect, afterEach, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../test/render';
import { emptyPulse } from '../test/pulseFixtures.js';
import CompanionGrowthToastStack from './CompanionGrowthToastStack';

const tickEvent = {
  pet_id: 1,
  species_slug: 'companion',
  species_name: 'Companion',
  species_sprite_key: 'companion',
  species_icon: '🐾',
  potion_slug: 'fire',
  potion_name: 'Fire',
  growth_added: 2,
  new_growth: 42,
  evolved: false,
  mount_id: null,
};

const evolveEvent = {
  ...tickEvent,
  pet_id: 2,
  growth_added: 2,
  new_growth: 100,
  evolved: true,
  mount_id: 99,
};

describe('CompanionGrowthToastStack', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders a tick event as a toast', async () => {
    renderWithProviders(<CompanionGrowthToastStack />, {
      pulse: emptyPulse({ companion_growth: { events: [tickEvent] } }),
    });
    await waitFor(() => {
      expect(screen.getByText(/fire companion grew/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/\+2/)).toBeInTheDocument();
    expect(screen.getByText(/42\/100/)).toBeInTheDocument();
  });

  it('escalates an evolved event into the PetCeremonyModal', async () => {
    renderWithProviders(<CompanionGrowthToastStack />, {
      pulse: emptyPulse({ companion_growth: { events: [evolveEvent] } }),
    });
    await waitFor(() => {
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });
    // The modal renders the species + potion in its headline. Also
    // confirm the toast strip stayed empty for evolve events.
    expect(screen.getByText(/fire companion/i)).toBeInTheDocument();
    expect(screen.getByText(/ready to ride/i)).toBeInTheDocument();
    expect(screen.queryByText(/companion grew/i)).not.toBeInTheDocument();
  });
});
