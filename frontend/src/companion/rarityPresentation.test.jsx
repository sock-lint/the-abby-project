import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import OwnedPetGrid from '../pages/bestiary/party/OwnedPetGrid';
import OwnedMountGrid from '../pages/bestiary/party/OwnedMountGrid';
import SpeciesDetailSheet from '../pages/bestiary/codex/SpeciesDetailSheet';
import { compareByRarityThenName } from '../pages/bestiary/party/party.constants';
import { totalRarityCounts } from '../pages/bestiary/codex/codex.constants';

vi.mock('../components/rpg/RpgSprite', () => ({ default: ({ alt }) => <img alt={alt} /> }));

const dragon = {
  id: 11, species: { id: 1, name: 'Dragon Spark', slug: 'meshtint-dragon', sprite_key: 'meshtint-dragon', rarity: 'legendary' },
  potion: { id: 1, name: 'Base', slug: 'base', rarity: 'common' }, growth_points: 20,
  can_breed: false, active_expedition: null,
};

describe('companion rarity presentation', () => {
  it('shows acquisition rarity on both growing and grown owned cards', () => {
    render(<><OwnedPetGrid pets={[dragon]} onSelect={vi.fn()} /><OwnedMountGrid mounts={[dragon]} /></>);
    expect(within(screen.getByRole('list', { name: 'Your companions' })).getByText('legendary')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Your grown pets' })).getByText('legendary')).toBeInTheDocument();
  });

  it('sorts by acquisition rarity and counts that tier in the codex', () => {
    const saved = { species: { name: 'Wolf', rarity: 'common' }, potion: { rarity: 'epic' } };
    expect([saved, dragon].sort(compareByRarityThenName)[0].id).toBe(11);
    const counts = totalRarityCounts([{ ...dragon.species, available_potions: [dragon.potion], owned_mount_potion_ids: [1] }]);
    expect(counts.legendary).toEqual({ earned: 1, total: 1 });
    expect(counts.common).toEqual({ earned: 0, total: 0 });
  });

  it('shows the same acquisition tier on the species grown form', () => {
    render(<SpeciesDetailSheet species={{ ...dragon.species, discovered: true, available_potions: [dragon.potion], owned_mount_potion_ids: [1] }} onClose={vi.fn()} />);
    expect(screen.getByText('legendary')).toBeInTheDocument();
  });
});
