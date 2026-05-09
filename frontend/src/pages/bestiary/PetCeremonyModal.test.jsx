import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../../test/render';
import PetCeremonyModal from './PetCeremonyModal';

const pet = {
  id: 1,
  species: { name: 'Phoenix', sprite_key: 'phoenix', icon: '🔥' },
  potion: { name: 'Cosmic', slug: 'cosmic' },
};

const breedParents = [
  { id: 10, species: { name: 'Wolf', sprite_key: 'wolf', icon: '🐺' }, potion: { name: 'Fire', slug: 'fire' } },
  { id: 11, species: { name: 'Dragon', sprite_key: 'dragon', icon: '🐉' }, potion: { name: 'Ice', slug: 'ice' } },
];

const breedResult = {
  egg_item_id: 99,
  egg_item_name: 'Wolf Egg',
  egg_item_icon: '🥚',
  egg_item_sprite_key: 'big-egg',
  potion_item_id: 100,
  potion_item_name: 'Fire Potion',
  potion_item_icon: '🧪',
  potion_item_sprite_key: '',
  picked_species: 'Wolf',
  picked_species_slug: 'wolf',
  picked_potion: 'Fire',
  picked_potion_slug: 'fire',
  chromatic: false,
  cooldown_days: 7,
};

describe('PetCeremonyModal', () => {
  it('renders hatch headline + dismiss button (mode=hatch)', () => {
    renderWithProviders(
      <PetCeremonyModal mode="hatch" pet={pet} onDismiss={() => {}} />,
    );
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText(/cosmic phoenix/i)).toBeInTheDocument();
    expect(screen.getByText(/has joined your party/i)).toBeInTheDocument();
  });

  it('renders evolve headline (mode=evolve)', () => {
    renderWithProviders(
      <PetCeremonyModal
        mode="evolve"
        species={pet.species}
        potion={pet.potion}
        onDismiss={() => {}}
      />,
    );
    expect(screen.getByText(/cosmic phoenix/i)).toBeInTheDocument();
    expect(screen.getByText(/ready to ride/i)).toBeInTheDocument();
  });

  it('renders breed alertdialog with the result egg name (mode=breed)', () => {
    renderWithProviders(
      <PetCeremonyModal
        mode="breed"
        parents={breedParents}
        result={breedResult}
        onDismiss={() => {}}
      />,
    );
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText(/wolf egg/i)).toBeInTheDocument();
    expect(screen.getByText(/paired with fire potion/i)).toBeInTheDocument();
    expect(screen.getByText(/parents resting for 7 days/i)).toBeInTheDocument();
    expect(screen.getByText(/a hybrid is conceived/i)).toBeInTheDocument();
  });

  it('shows chromatic kicker on chromatic breed', () => {
    renderWithProviders(
      <PetCeremonyModal
        mode="breed"
        parents={breedParents}
        result={{ ...breedResult, chromatic: true, picked_potion_slug: 'cosmic', potion_item_name: 'Cosmic Potion' }}
        onDismiss={() => {}}
      />,
    );
    expect(screen.getByText(/a chromatic blessing/i)).toBeInTheDocument();
    expect(screen.getByText(/the stars favored this pairing/i)).toBeInTheDocument();
  });

  it('calls onDismiss when Continue is clicked', async () => {
    const onDismiss = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <PetCeremonyModal mode="hatch" pet={pet} onDismiss={onDismiss} />,
    );
    await user.click(screen.getByRole('button', { name: /continue/i }));
    expect(onDismiss).toHaveBeenCalled();
  });

  it('renders nothing for unknown mode', () => {
    const { container } = renderWithProviders(
      <PetCeremonyModal mode="unknown" pet={pet} onDismiss={() => {}} />,
    );
    expect(container.querySelector('[role="alertdialog"]')).toBeNull();
  });
});

describe('PetCeremonyModal — phased sequence', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('hatch egg is rendered in phase 0 and replaced by the pet sprite by terminal phase', async () => {
    renderWithProviders(
      <PetCeremonyModal mode="hatch" pet={pet} onDismiss={() => {}} />,
    );
    // Phase 0: the egg sprite renders. RpgSprite falls through to emoji
    // fallback in the test env (catalog is empty), so we can find the egg
    // by its alt text.
    expect(screen.getByLabelText('egg')).toBeInTheDocument();

    // Advance through all phase timers (800 + 400 + 1200 = 2400ms).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    // Terminal phase: pet sprite is shown (alt = species name).
    expect(screen.getByLabelText('Phoenix')).toBeInTheDocument();
  });

  it('evolve renders the base sprite first then swaps to the mount form', async () => {
    renderWithProviders(
      <PetCeremonyModal
        mode="evolve"
        species={pet.species}
        potion={pet.potion}
        onDismiss={() => {}}
      />,
    );
    // Phase 0: base species sprite is visible.
    expect(screen.getAllByLabelText('Phoenix').length).toBeGreaterThan(0);

    // Advance past all phases (400 + 800 + 300 = 1500ms).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2200);
    });
    // Terminal phase: the mount form is visible (RpgSprite with the
    // ``-mount`` slug; it falls back to the base species sprite which
    // still uses the species name as its alt text).
    expect(screen.getAllByLabelText('Phoenix').length).toBeGreaterThan(0);
  });
});
