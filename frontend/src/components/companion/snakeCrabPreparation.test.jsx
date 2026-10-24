import { describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { renderWithProviders } from '../../test/render';
import { server } from '../../test/server';
import { useAuth } from '../../hooks/useApi';
import { SpriteCatalogContext } from '../../providers/spriteCatalog.context';
import { ownedAppearanceStages } from '../../companion/previewAccess';
import FamilyStagePreview from './FamilyStagePreview';
import CompanionPreview from './CompanionPreview';
import PetEvolutionGuide from './PetEvolutionGuide';
import { SNAKE_CRAB_SPECIES, stagedSnakeCrabFixture, snakeCrabCreature, snakeCrabEgg } from '../../test/snakeCrabReleaseFixture';

const scene = vi.hoisted(() => ({ props: null }));
vi.mock('../../companion/CompanionScene', () => ({ default: (props) => { scene.props = props; return <div data-testid="synthetic-scene" />; } }));
const forms = { 'meshtint-snake': ['Snakelet', 'Snake', 'Snake Naga'], 'meshtint-hermit-crab': ['Shell', 'Spike', 'Hermit King'] };
const pairs = SNAKE_CRAB_SPECIES.flatMap((species) => ['fire', 'ice'].map((potion) => [species, potion]));

function Ready({ children }) { const { user } = useAuth(); return user ? children : null; }
function withBasePortrait(children) {
  return <SpriteCatalogContext value={{ getSpriteMeta: () => ({ url: '/synthetic-base-only.png', frames: 1 }) }}>{children}</SpriteCatalogContext>;
}

describe('Snake/Hermit Crab missing artwork and explicit staging', () => {
  it.each(pairs)('keeps %s %s owned-care and return controls usable without borrowing Base artwork', async (species, potion) => {
    const user = userEvent.setup(), care = vi.fn(), claim = vi.fn(), fetch = vi.spyOn(globalThis, 'fetch');
    const creature = { ...snakeCrabCreature(species, potion), name: 'Maple', species: { slug: species, sprite_key: species, icon: '🐾' } };
    render(withBasePortrait(<CompanionPreview variant="primary" creature={creature} elemental={null} onInteract={care}>
      <button type="button" onClick={claim}>Claim saved expedition loot</button>
    </CompanionPreview>));
    expect(screen.getByRole('img', { name: 'Maple, your companion' }).tagName).toBe('SPAN');
    expect(screen.getByText('Artwork for this appearance is not available yet. Your companion and all controls are still available.')).toHaveAttribute('role', 'status');
    expect(screen.queryByText('View')).toBeNull();
    expect(screen.queryByTestId('synthetic-scene')).toBeNull();
    expect(document.querySelector('img[src="/synthetic-base-only.png"]')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Say hello to Maple' }));
    await user.click(screen.getByRole('button', { name: 'Claim saved expedition loot' }));
    expect(care).toHaveBeenCalledTimes(1);
    expect(claim).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls.filter(([url, options]) => String(url).endsWith('.glb') || options?.method === 'POST')).toHaveLength(0);
    fetch.mockRestore();
  });

  it.each(pairs)('shows exact %s %s stage names and explicit unavailable art while preserving its natural egg', async (species, potion) => {
    const user = userEvent.setup(), item = snakeCrabEgg(species), element = potion === 'fire' ? 'Fire' : 'Ice';
    renderWithProviders(withBasePortrait(<FamilyStagePreview item={item} potion={{ slug: potion, name: element }} elemental={null} />), { withAuth: false });
    expect(screen.getByRole('button', { name: 'Egg' })).toHaveAttribute('aria-pressed', 'true');
    for (const [index, stage] of ['Baby', 'Middle', 'Grown'].entries()) {
      await user.click(screen.getByRole('button', { name: stage }));
      expect(screen.getByRole('heading', { name: `${element} ${forms[species][index]}` })).toBeInTheDocument();
      expect(screen.getByRole('status')).toHaveTextContent(`${element} artwork is not available yet.`);
      expect(screen.getByRole('img', { name: `${element} ${forms[species][index]} artwork unavailable` }).tagName).toBe('SPAN');
      expect(screen.queryByRole('button', { name: 'Show 3D preview' })).toBeNull();
      expect(document.querySelector('img[src="/synthetic-base-only.png"]')).toBeNull();
    }
  });

  it.each(SNAKE_CRAB_SPECIES)('forwards staged %s bindings alongside the exact child allowance and clamps when the potion changes', async (species) => {
    const user = userEvent.setup(), staged = stagedSnakeCrabFixture(), item = snakeCrabEgg(species);
    const stable = { pets: [snakeCrabCreature(species, 'fire', 'middle')], mounts: [] };
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json({ id: 5, role: 'child', is_staff: false })));
    function Harness() {
      const [potion, setPotion] = useState({ slug: 'fire', name: 'Fire' });
      return <>
        <button type="button" onClick={() => setPotion({ slug: 'ice', name: 'Ice' })}>Choose Ice</button>
        <FamilyStagePreview item={item} potion={potion} elemental={staged}
          stages={ownedAppearanceStages(stable, { slug: species }, potion)} />
      </>;
    }
    renderWithProviders(<Ready><Harness /></Ready>);
    await user.click(await screen.findByRole('button', { name: 'Middle' }));
    expect(screen.getByRole('heading', { name: `Fire ${forms[species][1]}` })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Grown' })).toBeNull();
    const image = screen.getByRole('img', { name: `Fire ${forms[species][1]}` });
    expect(image).toHaveAttribute('src', expect.stringContaining('/synthetic-snake-crab/objects/'));
    await user.click(screen.getByRole('button', { name: 'Show 3D preview' }));
    await screen.findByTestId('synthetic-scene');
    expect(scene.props.appearance).toMatchObject({ key: `${species}-fire-middle`, defaultVariantId: 'source-rest-take', defaultAction: 'rest_native' });
    act(() => scene.props.onReady());
    await user.click(screen.getByText('More motions'));
    expect(screen.getByRole('button', { name: 'Play motion' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Choose Ice' }));
    expect(screen.queryByRole('button', { name: 'Baby' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Middle' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Grown' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Egg' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('heading', { name: `Ice ${forms[species][1]}` })).toBeNull();
    expect(screen.queryByTestId('synthetic-scene')).toBeNull();
  });

  it.each(SNAKE_CRAB_SPECIES)('withholds future %s form names from children while parents and staff keep their previews', async (species) => {
    for (const [account, restricted] of [[{ id: 5, role: 'child', is_staff: false }, true],
      [{ id: 6, role: 'parent', is_staff: false }, false], [{ id: 7, role: 'child', is_staff: true }, false]]) {
      server.use(http.get('*/api/auth/me/', () => HttpResponse.json(account)));
      const view = renderWithProviders(<Ready><PetEvolutionGuide creature={snakeCrabCreature(species, 'fire')} /></Ready>);
      const list = within(await screen.findByRole('list', { name: 'Pet growth stages' }));
      expect(list.getByText(`Baby · ${forms[species][0]}`)).toBeInTheDocument();
      if (restricted) {
        expect(list.getByText('Middle')).toBeInTheDocument();
        expect(list.queryByText(`Grown · ${forms[species][2]}`)).toBeNull();
      } else expect(list.getByText(`Grown · ${forms[species][2]}`)).toBeInTheDocument();
      view.unmount();
    }
  });

  it('keeps a failed exact synthetic portrait on its labelled fallback without trying Base', async () => {
    const user = userEvent.setup(), species = 'meshtint-hermit-crab';
    renderWithProviders(withBasePortrait(<FamilyStagePreview item={snakeCrabEgg(species)} potion={{ slug: 'ice', name: 'Ice' }}
      elemental={stagedSnakeCrabFixture()} />), { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Baby' }));
    const portrait = screen.getByRole('img', { name: 'Ice Shell' });
    expect(portrait).toHaveAttribute('src', expect.stringContaining('/synthetic-snake-crab/'));
    fireEvent.error(portrait);
    await waitFor(() => expect(screen.getByRole('img', { name: 'Ice Shell' }).tagName).toBe('SPAN'));
    expect(document.querySelector('img[src="/synthetic-base-only.png"]')).toBeNull();
  });
});
