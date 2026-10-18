import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders, screen, within } from '../../../test/render';
import OwnedPetGrid from './OwnedPetGrid';

const companion = (id, stage, growth, extra = {}) => ({
  id,
  species: { name: `Creature ${id}`, slug: `fixture-${id}`, sprite_key: `fixture-${id}`, icon: '🐾' },
  potion: { name: 'Base', slug: 'base', rarity: 'common' },
  lifecycle_stage: stage,
  growth_points: growth,
  evolved_to_mount: false,
  happiness_level: 'happy',
  ...extra,
});

describe('Owned companion growth progress', () => {
  it('shows growth remaining to Middle or Grown and keeps the saved stage until confirmation', () => {
    renderWithProviders(<OwnedPetGrid pets={[
      companion(1, 'baby', 35), companion(2, 'middle', 65),
      companion(3, 'middle', 100), companion(4, 'grown', 100, { evolved_to_mount: true }),
    ]} onSelect={vi.fn()} />, { withAuth: false });

    const baby = within(screen.getByRole('button', { name: 'Care for Base Creature 1' }));
    expect(baby.getByText('Baby')).toBeInTheDocument();
    expect(baby.getByText('15 growth to Middle')).toBeInTheDocument();
    const middle = within(screen.getByRole('button', { name: 'Care for Base Creature 2' }));
    expect(middle.getByText('Middle')).toBeInTheDocument();
    expect(middle.getByText('35 growth to Grown')).toBeInTheDocument();
    const pending = within(screen.getByRole('button', { name: 'Care for Base Creature 3' }));
    expect(pending.getByText('Middle')).toBeInTheDocument();
    expect(pending.queryByText('Grown')).toBeNull();
    expect(pending.queryByText(/growth to/)).toBeNull();
    const grown = within(screen.getByRole('button', { name: 'Care for Base Creature 4' }));
    expect(grown.getByText('Grown')).toBeInTheDocument();
    expect(grown.queryByText(/growth to/)).toBeNull();
  });

  it('omits next-stage promises for unknown stages or missing growth values', () => {
    renderWithProviders(<OwnedPetGrid pets={[
      companion(1, 'future-stage', 35), companion(2, 'baby', null),
    ]} onSelect={vi.fn()} />, { withAuth: false });
    expect(screen.queryByText(/growth to/)).toBeNull();
  });
});
