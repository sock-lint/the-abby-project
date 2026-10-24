import { act, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/server';
import { useAuth } from '../../hooks/useApi';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/render';
import { stagedElementalFixture, syntheticElemental } from '../../test/elementalReleaseFixture';
import CompanionPreview from './CompanionPreview';
import FamilyStagePreview from './FamilyStagePreview';
import RpgSprite from '../rpg/RpgSprite';
import CatalogIcon from '../rpg/CatalogIcon';

const scene = vi.hoisted(() => ({ props: null }));
vi.mock('../../companion/CompanionScene', () => ({ default: (props) => {
  scene.props = props;
  return <div data-testid="evaluation-scene" />;
} }));
beforeEach(() => { scene.props = null; });

// Explicit fixtures use the real resolvers and components. They do not change
// the application's active lock or install private files in a Vite source tree.
describe('Explicit private elemental presentation', () => {
  it('renders an explicitly supplied appearance, preserves its saved element at the destination stage and keeps care controls', async () => {
    const staged = stagedElementalFixture(true);
    const view = renderWithProviders(<CompanionPreview variant="primary" elemental={staged}
      creature={syntheticElemental('meshtint-mushroom', 'fire', 'baby')}><button>Existing care control</button></CompanionPreview>, { withAuth: false });
    await screen.findByTestId('evaluation-scene');
    expect(scene.props.appearance.selection).toMatchObject({ species_slug: 'meshtint-mushroom', potion_slug: 'fire', lifecycle_stage: 'baby' });
    expect(screen.getByRole('button', { name: 'Existing care control' })).toBeEnabled();
    act(() => scene.props.onReady());
    view.rerender(<CompanionPreview variant="primary" elemental={staged} creature={syntheticElemental('meshtint-mushroom', 'fire', 'grown')} />);
    await waitFor(() => expect(scene.props.appearance.stage).toBe('grown'));
    expect(scene.props.appearance.selection.potion_slug).toBe('fire');
    expect(scene.props.evolution).toBeNull();
  });

  it('uses supplied Hatchery stage art and portraits while retaining the natural egg identity', async () => {
    const user = userEvent.setup(), staged = stagedElementalFixture(true);
    const item = { id: 42, item_type: 'egg', slug: 'meshtint-mushroom-egg', pet_species_slug: 'meshtint-mushroom',
      metadata: { species: 'meshtint-mushroom' }, name: 'Mushroom Egg' };
    renderWithProviders(<FamilyStagePreview elemental={staged} item={item} potion={{ slug: 'ice', name: 'Ice' }} />, { withAuth: false });
    expect(screen.getByRole('button', { name: 'Egg' })).toHaveAttribute('aria-pressed', 'true');
    expect(scene.props).toBeNull();
    for (const [stage, form] of [['Baby', 'Mushroom'], ['Middle', 'Fungi'], ['Grown', 'Toadstool']]) {
      await user.click(screen.getByRole('button', { name: stage }));
      expect(screen.getByRole('img', { name: `Ice ${form}` }).getAttribute('src')).toContain('/synthetic-elemental/');
      await user.click(screen.getByRole('button', { name: 'Show 3D preview' }));
      await screen.findByTestId('evaluation-scene');
      expect(scene.props.appearance.selection).toMatchObject({ potion_slug: 'ice', lifecycle_stage: stage.toLowerCase() });
    }
    expect(item.slug).toBe('meshtint-mushroom-egg');
  });

  it('uses explicit stage portraits and challenge artwork without recoloring or registering an offer', () => {
    const staged = stagedElementalFixture(true);
    const binding = staged.release.appearance_bindings.stages.find((entry) => entry.species_slug === 'meshtint-mushroom' && entry.potion_slug === 'ice');
    renderWithProviders(<><RpgSprite elemental={staged} spriteKey="meshtint-mushroom" potionSlug="ice" alt="Private portrait" />
      <CatalogIcon elemental={staged} assetId={binding.portrait_asset_id} alt="Private catalog art" icon="🐾" /></>, { withAuth: false });
    for (const name of ['Private portrait', 'Private catalog art']) {
      expect(screen.getByRole('img', { name }).getAttribute('src')).toContain('/synthetic-elemental/');
      expect(screen.getByRole('img', { name }).style.filter).toBeFalsy();
    }
  });
});

describe('Explicit elemental art under the child surprise allowance', () => {
  const item = { id: 43, item_type: 'egg', slug: 'meshtint-mushroom-egg', pet_species_slug: 'meshtint-mushroom',
    metadata: { species: 'meshtint-mushroom' }, name: 'Mushroom Egg' };
  const potion = { slug: 'ice', name: 'Ice' };

  it('clamps an explicitly staged elemental Grown selection when one mounted preview loses its allowance', async () => {
    const user = userEvent.setup(), staged = stagedElementalFixture(true);
    function Harness() {
      const [stages, setStages] = useState(['baby', 'middle', 'grown']);
      return <>
        <button type="button" onClick={() => setStages(['baby'])}>Limit allowance</button>
        <button type="button" onClick={() => setStages(['baby', 'middle', 'grown'])}>Restore allowance</button>
        <FamilyStagePreview elemental={staged} item={item} potion={potion} stages={stages} />
      </>;
    }
    renderWithProviders(<Harness />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Grown' }));
    expect(screen.getByRole('img', { name: 'Ice Toadstool' }).getAttribute('src')).toContain('/synthetic-elemental/');
    await user.click(screen.getByRole('button', { name: 'Limit allowance' }));
    expect(screen.queryByRole('img', { name: 'Ice Toadstool' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Grown' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Egg' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: 'Restore allowance' }));
    expect(screen.getByRole('button', { name: 'Grown' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('never lets an explicit art source grant a child a stage', async () => {
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json({ id: 5, role: 'child', is_staff: false })));
    function Ready({ children }) { const { user } = useAuth(); return user ? children : null; }
    renderWithProviders(<Ready><FamilyStagePreview elemental={stagedElementalFixture(true)} item={item} potion={potion} initialStage="grown" /></Ready>);
    expect(await screen.findByRole('button', { name: 'Egg' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('button', { name: 'Baby' })).toBeNull();
    expect(screen.queryByText(/Toadstool|Fungi/)).toBeNull();
    expect(scene.props).toBeNull();
  });
});
