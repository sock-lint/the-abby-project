import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import PetCeremonyModal from './PetCeremonyModal';

vi.mock('../../components/rpg/CatalogIcon', () => ({ default: ({ assetId, alt }) => <span role="img" aria-label={alt} data-asset-id={assetId} /> }));
vi.mock('../../components/rpg/RpgSprite', () => ({ default: ({ spriteKey, potionSlug, alt }) => <span role="img" aria-label={alt} data-sprite-key={spriteKey} data-potion={potionSlug} /> }));

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => vi.useRealTimers());

describe('Elemental hatch and evolution celebrations', () => {
  const snakeCrab = [
    ['meshtint-snake', 'Snakelet', 'Snake', 'Snake Naga', 'snake-egg-portrait'],
    ['meshtint-hermit-crab', 'Shell', 'Spike', 'Hermit King', 'hermit-crab-egg-portrait'],
  ].flatMap((family) => ['fire', 'ice'].map((potion) => [...family, potion]));

  it.each(snakeCrab)('preserves the natural %s egg and exact %s Baby appearance through the ordinary hatch celebration', async (slug, baby, _middle, _grown, eggId, element) => {
    const species = { slug, sprite_key: slug, name: baby }, potion = { slug: element, name: element };
    renderWithProviders(<PetCeremonyModal mode="hatch" pet={{ id: 91, species, potion }} onDismiss={() => {}} />, { withAuth: false });
    expect(screen.getByRole('img', { name: 'egg' })).toHaveAttribute('data-asset-id', eggId);
    await act(async () => { await vi.advanceTimersByTimeAsync(1300); });
    expect(screen.getByRole('img', { name: baby })).toHaveAttribute('data-sprite-key', slug);
    expect(screen.getByRole('img', { name: baby })).toHaveAttribute('data-potion', element);
  });

  it.each(snakeCrab)('shows the confirmed %s %s Baby immediately with reduced motion', (slug, baby, _middle, _grown, _eggId, element) => {
    renderWithProviders(<PetCeremonyModal mode="hatch" pet={{ id: 91, species: { slug, sprite_key: slug, name: baby }, potion: { slug: element, name: element } }}
      reducedMotion onDismiss={() => {}} />, { withAuth: false });
    expect(screen.queryByRole('img', { name: 'egg' })).toBeNull();
    expect(screen.getByRole('img', { name: baby })).toHaveAttribute('data-sprite-key', slug);
    expect(screen.getByRole('img', { name: baby })).toHaveAttribute('data-potion', element);
  });

  it.each(snakeCrab)('preserves confirmed %s %s Middle and Grown fallback sprites during evolution', async (slug, baby, middle, grown, _eggId, element) => {
    renderWithProviders(<PetCeremonyModal mode="evolve" species={{ slug, sprite_key: slug, name: baby }} potion={{ slug: element, name: element }}
      fromStage="middle" onDismiss={() => {}} />, { withAuth: false });
    expect(screen.getByRole('img', { name: middle })).toHaveAttribute('data-sprite-key', `${slug}-middle`);
    await act(async () => { await vi.advanceTimersByTimeAsync(1700); });
    expect(screen.getByRole('img', { name: grown })).toHaveAttribute('data-sprite-key', `${slug}-mount`);
    expect(screen.getByRole('img', { name: grown })).toHaveAttribute('data-potion', element);
  });

  it.each(snakeCrab)('shows the confirmed %s %s Grown fallback directly with reduced motion', (slug, baby, middle, grown, _eggId, element) => {
    renderWithProviders(<PetCeremonyModal mode="evolve" species={{ slug, sprite_key: slug, name: baby }} potion={{ slug: element, name: element }}
      fromStage="middle" reducedMotion onDismiss={() => {}} />, { withAuth: false });
    expect(screen.queryByRole('img', { name: middle })).toBeNull();
    expect(screen.getByRole('img', { name: grown })).toHaveAttribute('data-sprite-key', `${slug}-mount`);
    expect(screen.getByRole('img', { name: grown })).toHaveAttribute('data-potion', element);
  });

  it.each(['fire', 'ice'])('keeps the natural Wolf egg before revealing the exact %s baby', async (slug) => {
    const potion = { slug, name: slug === 'fire' ? 'Fire' : 'Ice' };
    const pet = { id: 1, species: { slug: 'meshtint-wolf', sprite_key: 'meshtint-wolf', name: 'Wolf' }, potion };
    renderWithProviders(<PetCeremonyModal mode="hatch" pet={pet} onDismiss={() => {}} />, { withAuth: false });
    expect(screen.getByRole('img', { name: 'egg' })).toHaveAttribute('data-asset-id', 'wolf-egg-portrait');
    await act(async () => { await vi.advanceTimersByTimeAsync(1300); });
    expect(screen.getByRole('img', { name: 'Wolf Pup' })).toHaveAttribute('data-sprite-key', 'meshtint-wolf');
    expect(screen.getByRole('img', { name: 'Wolf Pup' })).toHaveAttribute('data-potion', slug);
  });

  it.each(['fire', 'ice'])('uses the confirmed %s Fledgling source and Bird destination in the 2D fallback', async (slug) => {
    const species = { slug: 'chick', sprite_key: 'cute-chick', name: 'Chick' };
    renderWithProviders(<PetCeremonyModal mode="evolve" species={species} potion={{ slug, name: slug }} fromStage="middle" onDismiss={() => {}} />, { withAuth: false });
    expect(screen.getByRole('img', { name: 'Fledgling' })).toHaveAttribute('data-sprite-key', 'cute-chick-fledgling');
    await act(async () => { await vi.advanceTimersByTimeAsync(1700); });
    expect(screen.getByRole('img', { name: 'Bird' })).toHaveAttribute('data-sprite-key', 'cute-chick-mount');
    expect(screen.getByRole('img', { name: 'Bird' })).toHaveAttribute('data-potion', slug);
  });

  it.each(['fire', 'ice'])('shows the confirmed %s Bird immediately with reduced motion', (slug) => {
    renderWithProviders(<PetCeremonyModal mode="evolve" species={{ slug: 'chick', sprite_key: 'cute-chick', name: 'Chick' }}
      potion={{ slug, name: slug }} fromStage="middle" reducedMotion onDismiss={() => {}} />, { withAuth: false });
    expect(screen.queryByRole('img', { name: 'Fledgling' })).toBeNull();
    expect(screen.getByRole('img', { name: 'Bird' })).toHaveAttribute('data-sprite-key', 'cute-chick-mount');
    expect(screen.getByRole('img', { name: 'Bird' })).toHaveAttribute('data-potion', slug);
  });
});
