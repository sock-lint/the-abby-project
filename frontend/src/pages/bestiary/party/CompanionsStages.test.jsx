import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, within } from '../../../test/render';
import { server } from '../../../test/server';
import Companions from './Companions';

vi.mock('../../../components/companion/CompanionPreview', () => ({
  default: ({ children }) => <section aria-label="Companion home">{children}</section>,
}));

const companion = (id, name, stage, growth, extra = {}) => ({
  id,
  catalog_available: true,
  species: { id, slug: `fixture-${id}`, sprite_key: `fixture-${id}`, name, icon: '🐾' },
  potion: { id: 1, name: 'Base', slug: 'base', rarity: 'common' },
  lifecycle_stage: stage,
  growth_points: growth,
  evolved_to_mount: false,
  happiness_level: 'happy',
  ...extra,
});

describe('Companion growth filters', () => {
  it('filters Baby and Middle by saved server stage while keeping earlier pets in Saved collection', async () => {
    const baby = companion(1, 'Small Fox', 'baby', 99, { is_active: true });
    const middle = companion(2, 'Growing Wolf', 'middle', 0);
    const grown = companion(3, 'Grown Drake', 'grown', 100, { evolved_to_mount: true });
    const unknown = companion(4, 'Unfamiliar Creature', 'future-stage', 50);
    const saved = companion(5, 'Earlier Cat', 'middle', 75, { catalog_available: false });
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({
        pets: [baby, middle, grown, unknown, saved], mounts: [], total_possible: 4,
      })),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    const { user } = renderWithProviders(<Companions />);
    expect(await screen.findByRole('tab', { name: 'All (4)' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Active (1)' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Baby (1)' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Middle (1)' })).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Middle (1)' }));
    let collection = within(screen.getByRole('list', { name: 'Your companions' }));
    expect(collection.getByRole('button', { name: 'Care for Base Growing Wolf' })).toBeInTheDocument();
    expect(collection.getAllByRole('listitem')).toHaveLength(1);
    expect(within(screen.getByRole('region', { name: 'Saved collection' })).getByRole('button', {
      name: 'Care for Base Earlier Cat',
    })).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Baby (1)' }));
    collection = within(screen.getByRole('list', { name: 'Your companions' }));
    expect(collection.getByRole('button', { name: 'Care for Base Small Fox' })).toBeInTheDocument();
    expect(collection.getAllByRole('listitem')).toHaveLength(1);
    expect(screen.getByRole('tab', { name: 'Baby (1)' })).toHaveAttribute('aria-selected', 'true');
  });
});
