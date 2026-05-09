import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../../test/render';
import PetCeremonyModal from './PetCeremonyModal';

const pet = {
  id: 1,
  species: { name: 'Phoenix', sprite_key: 'phoenix', icon: '🔥' },
  potion: { name: 'Cosmic', slug: 'cosmic' },
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
