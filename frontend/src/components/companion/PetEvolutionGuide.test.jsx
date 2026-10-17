import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import PetEvolutionGuide from './PetEvolutionGuide';

const creature = { id: 1, species: { slug: 'chick', sprite_key: 'cute-chick' }, potion: { slug: 'base' }, evolution_stage: 'fledgling', growth_points: 65 };

describe('PetEvolutionGuide', () => {
  it('includes the egg before all three owned stages and highlights only the confirmed middle stage', () => {
    render(<PetEvolutionGuide creature={creature} />);
    const steps = within(screen.getByRole('list', { name: 'Pet growth stages' })).getAllByRole('listitem');
    expect(steps).toHaveLength(4);
    expect(steps[0]).toHaveTextContent('Egg');
    expect(steps[0]).not.toHaveAttribute('aria-current');
    expect(steps[1]).not.toHaveAttribute('aria-current');
    expect(steps[1]).toHaveTextContent('Baby');
    expect(steps[2]).toHaveAttribute('aria-current', 'step');
    expect(steps[2]).toHaveTextContent('Middle');
    expect(steps[2]).toHaveTextContent('Fledgling');
    expect(steps[3]).toHaveTextContent('Grown');
    expect(steps[3]).not.toHaveAttribute('aria-current');
  });

  it.each(['fox', 'new-creature'])('shows the complete lifecycle for %s without borrowing Bird forms', (slug) => {
    render(<PetEvolutionGuide creature={{ ...creature, species: { slug, sprite_key: slug }, evolution_stage: null, lifecycle_stage: 'middle' }} />);
    const steps = within(screen.getByRole('list', { name: 'Pet growth stages' })).getAllByRole('listitem');
    expect(steps).toHaveLength(4);
    expect(steps[2]).toHaveAttribute('aria-current', 'step');
    expect(screen.queryByText(/Fledgling|Chick|Bird/)).toBeNull();
  });

  it('shows an inventory egg as the current stage before hatching without inventing owned growth', () => {
    render(<PetEvolutionGuide species={{ name: 'Fox', slug: 'fox' }} currentStage="egg" />);
    const steps = within(screen.getByRole('list', { name: 'Pet growth stages' })).getAllByRole('listitem');
    expect(steps[0]).toHaveAttribute('aria-current', 'step');
    expect(steps[0]).toHaveTextContent(/hatch/i);
    expect(steps[1]).not.toHaveAttribute('aria-current');
  });

  it('keeps the baby stage until a response confirms middle growth and the grown stage until confirmed evolution', () => {
    render(<PetEvolutionGuide creature={{ id: 2, species: { slug: 'fox' }, growth_points: 100, evolved_to_mount: false }} />);
    const steps = within(screen.getByRole('list', { name: 'Pet growth stages' })).getAllByRole('listitem');
    expect(steps[1]).toHaveAttribute('aria-current', 'step');
    expect(steps[3]).not.toHaveAttribute('aria-current');
  });
});
