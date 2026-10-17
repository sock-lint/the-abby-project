import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import PetEvolutionGuide from './PetEvolutionGuide';

const creature = { id: 1, species: { slug: 'chick', sprite_key: 'cute-chick' }, potion: { slug: 'base' }, evolution_stage: 'fledgling', growth_points: 65 };

describe('PetEvolutionGuide', () => {
  it('keeps each of the three stages readable and highlights only the confirmed stage', () => {
    render(<PetEvolutionGuide creature={creature} />);
    const steps = within(screen.getByRole('list', { name: 'Pet growth stages' })).getAllByRole('listitem');
    expect(steps).toHaveLength(3);
    expect(steps[0]).not.toHaveAttribute('aria-current');
    expect(steps[1]).toHaveAttribute('aria-current', 'step');
    expect(steps[1]).toHaveTextContent('Fledgling');
    expect(steps[2]).not.toHaveAttribute('aria-current');
  });

  it('does not advertise bird stages for a saved species or an unavailable potion', () => {
    const view = render(<PetEvolutionGuide creature={{ ...creature, species: { slug: 'fox', sprite_key: 'fox' } }} />);
    expect(screen.queryByRole('list')).toBeNull();
    view.rerender(<PetEvolutionGuide creature={{ ...creature, potion: { slug: 'fire' } }} />);
    expect(screen.queryByRole('list')).toBeNull();
  });
});
