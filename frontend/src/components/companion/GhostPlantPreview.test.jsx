import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FamilyStagePreview from './FamilyStagePreview';
import PetEvolutionGuide from './PetEvolutionGuide';
import { ownedAppearanceStages } from '../../companion/previewAccess';
import { useAuth } from '../../hooks/useApi';
import { server } from '../../test/server';
import { renderWithProviders } from '../../test/render';
import { ghostPlantCreature, ghostPlantEgg, stagedGhostPlantFixture } from '../../test/ghostPlantReleaseFixture';

const families = [
  ['meshtint-ghost', 'Ghost', 'Spook', 'Phantom'],
  ['meshtint-potted-plant', 'Seed', 'Sprout', 'Flower Pot Monster'],
];

describe('synthetic Ghost/Potted Plant stage previews before private artwork', () => {
  it.each(families.flatMap((family) => ['fire', 'ice'].map((potion) => [...family, potion])))(
    'keeps exact %s %s stage art explicit and clamps a changed child allowance', async (slug, baby, middle, grown, initialPotion) => {
    const alternate = initialPotion === 'fire' ? 'ice' : 'fire';
    const staged = stagedGhostPlantFixture(), item = { ...ghostPlantEgg(slug), name: `${baby} Egg` };
    const mature = ghostPlantCreature(slug, initialPotion, 'middle');
    // A large counter still grants only the server-confirmed Baby stage.
    const young = ghostPlantCreature(slug, alternate, 'baby');
    const stable = { pets: [mature, young], mounts: [] };
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json({ id: 5, role: 'child', is_staff: false })));
    function Harness() {
      const { user } = useAuth();
      const [element, setElement] = useState(initialPotion);
      if (!user) return null;
      const potion = { slug: element, name: element === 'fire' ? 'Fire' : 'Ice' };
      const species = mature.species;
      const stages = ownedAppearanceStages(stable, species, potion);
      return <>
        <button type="button" onClick={() => setElement(alternate)}>Switch appearance</button>
        <FamilyStagePreview item={item} potion={potion} stages={stages} elemental={staged} />
        <PetEvolutionGuide species={species} potion={potion} revealedStages={stages} />
      </>;
    }
    renderWithProviders(<Harness />);
    const user = userEvent.setup();
    const initialName = initialPotion === 'fire' ? 'Fire' : 'Ice';
    const alternateName = alternate === 'fire' ? 'Fire' : 'Ice';
    await user.click(await screen.findByRole('button', { name: 'Middle' }));
    expect(screen.getByRole('heading', { name: `${initialName} ${middle}` })).toBeInTheDocument();
    const portrait = screen.getByRole('img', { name: `${initialName} ${middle}` });
    expect(portrait).toHaveAttribute('src', expect.stringContaining('/synthetic-ghost-plant/'));
    expect(portrait.style.filter).toBe('');
    expect(screen.queryByRole('button', { name: 'Grown' })).toBeNull();
    expect(screen.queryByText(new RegExp(grown))).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Switch appearance' }));
    expect(screen.getByRole('button', { name: 'Egg', exact: true })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('heading', { name: `${baby} Egg` })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Middle' })).toBeNull();
    expect(screen.queryByText(new RegExp(middle))).toBeNull();
    expect(screen.queryByText(new RegExp(grown))).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Baby' }));
    expect(screen.getByRole('heading', { name: `${alternateName} ${baby}` })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: `${alternateName} ${baby}` })).toHaveAttribute('src', expect.stringContaining('/synthetic-ghost-plant/'));
    const guide = within(screen.getByRole('list', { name: 'Pet growth stages' }));
    expect(guide.getByText(`Baby · ${baby}`)).toBeInTheDocument();
    expect(guide.getByText('Middle', { exact: true })).toBeInTheDocument();
    expect(guide.getByText('Grown', { exact: true })).toBeInTheDocument();
    });
});
