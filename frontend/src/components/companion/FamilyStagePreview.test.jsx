import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/render';
import FamilyStagePreview from './FamilyStagePreview';
import { rosterEgg } from '../../test/rosterReleaseFixture';
import { resolveElementalPreviewAppearance } from '../../companion/sharedElementalRelease';
import { resolveElementalPortrait } from '../../companion/sharedElementalPortraits';

vi.mock('../../companion/sharedElementalRelease', async () => ({
  ...await vi.importActual('../../companion/sharedElementalRelease'),
  resolveElementalPreviewAppearance: vi.fn(() => null),
}));
vi.mock('../../companion/sharedElementalPortraits', () => ({
  resolveElementalPortrait: vi.fn(() => null), resolveElementalCatalogIcon: vi.fn(() => null),
}));
beforeEach(() => {
  vi.mocked(resolveElementalPreviewAppearance).mockReset().mockReturnValue(null);
  vi.mocked(resolveElementalPortrait).mockReset().mockReturnValue(null);
});

describe('Hatchery family stage previews', () => {
  it.each([
    ['chick', 'fire'], ['chick', 'ice'], ['meshtint-wolf', 'fire'], ['meshtint-wolf', 'ice'],
    ['meshtint-dragon', 'fire'], ['meshtint-dragon', 'ice'], ['meshtint-mushroom', 'fire'], ['meshtint-mushroom', 'ice'],
  ])('previews exact installed %s %s forms and portraits while retaining the original egg', async (species, element) => {
    const user = userEvent.setup(), potion = { slug: element, name: element === 'fire' ? 'Fire' : 'Ice' };
    const item = species === 'chick'
      ? { id: 77, slug: 'chick-egg', item_type: 'egg', pet_species_slug: 'chick', metadata: { species: 'chick' }, name: 'Chick Egg' }
      : { ...rosterEgg(), slug: `${species}-egg`, pet_species_slug: species, metadata: { species }, name: `${species} Egg` };
    vi.mocked(resolveElementalPreviewAppearance).mockImplementation((_item, stage) => ({ key: `${species}-${element}-${stage}`, motions: [] }));
    vi.mocked(resolveElementalPortrait).mockImplementation((key, slug) => ({ url: `/synthetic/${slug}/${key}.png`, frames: 1 }));
    const fetch = vi.spyOn(globalThis, 'fetch');
    renderWithProviders(<FamilyStagePreview item={item} potion={potion} />, { withAuth: false });
    expect(screen.getByRole('button', { name: 'Egg' })).toHaveAttribute('aria-pressed', 'true');
    expect(resolveElementalPreviewAppearance).not.toHaveBeenCalled();
    const forms = { chick: ['Chick', 'Fledgling', 'Bird'], 'meshtint-wolf': ['Wolf Pup', 'Wolf', 'Werewolf'],
      'meshtint-dragon': ['Dragonling', 'Dragon', 'Elder Dragon'], 'meshtint-mushroom': ['Mushroom', 'Fungi', 'Toadstool'] }[species];
    for (const [index, stage] of ['baby', 'middle', 'grown'].entries()) {
      await user.click(screen.getByRole('button', { name: stage[0].toUpperCase() + stage.slice(1) }));
      expect(screen.getByRole('heading', { name: `${potion.name} ${forms[index]}` })).toBeInTheDocument();
      expect(resolveElementalPreviewAppearance).toHaveBeenLastCalledWith(item, stage, potion);
      expect(screen.getByRole('button', { name: 'Show 3D preview' })).toBeEnabled();
      expect(screen.getByRole('img', { name: `${potion.name} ${forms[index]}` })).toHaveAttribute('src', expect.stringContaining(`/synthetic/${element}/`));
    }
    expect(fetch.mock.calls.filter(([url, options]) => String(url).endsWith('.glb') || options?.method === 'POST')).toHaveLength(0);
    fetch.mockRestore();
  });

  it('previews all four exact family stages without loading a model or changing owned progression', async () => {
    const user = userEvent.setup(), fetch = vi.spyOn(globalThis, 'fetch');
    renderWithProviders(<FamilyStagePreview item={{ ...rosterEgg(), name: 'Wolf Egg' }} />, { withAuth: false });
    expect(screen.getByRole('button', { name: 'Egg' })).toHaveAttribute('aria-pressed', 'true');
    for (const [stage, name] of [['Baby', 'Wolf Pup'], ['Middle', 'Wolf'], ['Grown', 'Werewolf']]) {
      await user.click(screen.getByRole('button', { name: stage }));
      expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    }
    expect(fetch.mock.calls.filter(([url, options]) => String(url).endsWith('.glb') || options?.method === 'POST')).toHaveLength(0);
    fetch.mockRestore();
  });

  it('never turns a conflicting or Dummy egg into a roster preview', () => {
    renderWithProviders(<FamilyStagePreview item={{ ...rosterEgg(), pet_species_slug: 'meshtint-training-dummy' }} />, { withAuth: false });
    expect(screen.queryByRole('button', { name: 'Baby' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Show 3D preview' })).toBeNull();
  });

  it.each(['fire', 'ice'])('never presents Base artwork as a missing %s appearance', async (element) => {
    const user = userEvent.setup();
    const name = element === 'fire' ? 'Fire' : 'Ice';
    renderWithProviders(<FamilyStagePreview item={{ ...rosterEgg(), name: 'Wolf Egg' }} potion={{ slug: element, name }} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Baby' }));
    expect(screen.getByRole('heading', { name: `${name} Wolf Pup` })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(`${name} artwork is not available yet.`);
    expect(screen.queryByRole('button', { name: 'Show 3D preview' })).toBeNull();
    expect(document.querySelector('img[src*="wolf"]')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Grown' }));
    expect(screen.getByRole('heading', { name: `${name} Werewolf` })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Grown' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('names unprepared Ice Dragon stages without borrowing Base Fire names or artwork', async () => {
    const user = userEvent.setup(), species = 'meshtint-dragon';
    renderWithProviders(<FamilyStagePreview item={{ ...rosterEgg(), slug: `${species}-egg`, pet_species_slug: species, metadata: { species }, name: 'Dragon Egg' }} potion={{ slug: 'ice', name: 'Ice' }} />, { withAuth: false });
    for (const [stage, form] of [['Baby', 'Dragonling'], ['Middle', 'Dragon'], ['Grown', 'Elder Dragon']]) {
      await user.click(screen.getByRole('button', { name: stage }));
      expect(screen.getByRole('heading', { name: `Ice ${form}` })).toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveTextContent('Ice artwork is not available yet.');
      expect(screen.queryByRole('button', { name: 'Show 3D preview' })).toBeNull();
      expect(screen.getByRole('img', { name: `Ice ${form} artwork unavailable` })).toHaveTextContent('🐾');
    }
  });
});
