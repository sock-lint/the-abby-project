import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CompanionPreview from './CompanionPreview';
import { syntheticElemental } from '../../test/elementalReleaseFixture';

const scene = vi.hoisted(() => ({ props: null, crash: false }));
vi.mock('../../companion/appearance', async () => {
  const actual = await vi.importActual('../../companion/appearance');
  const { stagedElementalFixture } = await import('../../test/elementalReleaseFixture');
  const manifest = {
    schema_version: 1,
    bindings: [{ species_slug: 'chick', species_sprite_key: 'cute-chick', potion_slug: 'base', pet: 'chick', evolved: 'bird', mount: 'bird' }],
    models: { chick: { file: 'chick.glb', interaction_clips: { play: { file: 'hop.glb', clip: 'Hop' }, left: { file: 'turn.glb', clip: 'Left' }, right: { file: 'turn.glb', clip: 'Right' } } }, bird: { file: 'bird.glb', interaction_clips: { play: { file: 'fly.glb', clip: 'Fly' } } } },
  };
  const urls = { './licensed/chick.glb': '/test-chick.glb', './licensed/bird.glb': '/test-bird.glb', './licensed/hop.glb': '/test-hop.glb', './licensed/fly.glb': '/test-fly.glb', './licensed/turn.glb': '/test-turn.glb' };
  return { ...actual, resolveAppearance: (creature, kind) => actual.resolveAppearance(creature, kind, manifest, urls, undefined, undefined, stagedElementalFixture()) };
});
vi.mock('../../companion/modelLoader', () => ({ resetModels: vi.fn() }));
vi.mock('../../companion/CompanionScene', () => ({ default: (props) => {
  scene.props = props;
  if (scene.crash) throw new Error('Synthetic model load failure');
  return <div data-testid="optional-scene" />;
} }));

const pet = { id: 1, species: { name: 'Chick', slug: 'chick', sprite_key: 'cute-chick', icon: '🐤' }, potion: { name: 'Base', slug: 'base' }, growth_points: 99, evolved_to_mount: false };
beforeEach(() => { scene.props = null; scene.crash = false; vi.unstubAllEnvs(); });

describe('Optional companion preview', () => {
  it.each([['fire', 'baby', 'middle'], ['ice', 'middle', 'grown'], ['fire', 'baby', 'grown']])('queues exact %s Chick %s → %s transitions from saved lifecycle stages', async (potion, from, to) => {
    const start = syntheticElemental('chick', potion, from);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const view = render(<CompanionPreview variant="primary" creature={start} />);
    await screen.findByTestId('optional-scene');
    expect(scene.props.appearance.key).toBe(`chick-${potion}-${from}`);
    expect(scene.props.evolution).toBeNull();
    view.rerender(<CompanionPreview variant="primary" creature={{ ...start, growth_points: 100 }} />);
    expect(scene.props.evolution).toBeNull();
    expect(scene.props.appearance.stage).toBe(from);
    view.rerender(<CompanionPreview variant="primary" creature={syntheticElemental('chick', potion, to)} />);
    await waitFor(() => expect(scene.props.appearance.stage).toBe(to));
    expect(scene.props.evolution).toEqual({ id: 1, from, to });
    const receipt = scene.props.evolution;
    view.rerender(<CompanionPreview variant="primary" creature={{ ...syntheticElemental('chick', potion, to), last_fed_at: '2026-10-20T12:00:00Z' }} />);
    expect(scene.props.evolution).toBe(receipt);
    expect(fetchSpy.mock.calls.filter(([, options]) => options?.method && options.method !== 'GET')).toHaveLength(0);
    fetchSpy.mockRestore();
  });

  it('selects a confirmed Wolf target with no invented transition and resets elemental identity on potion changes', async () => {
    const start = syntheticElemental('meshtint-wolf', 'fire', 'baby');
    const view = render(<CompanionPreview variant="primary" creature={start} />);
    await screen.findByTestId('optional-scene');
    expect(scene.props.appearance.key).toBe('meshtint-wolf-fire-baby');
    view.rerender(<CompanionPreview variant="primary" creature={syntheticElemental('meshtint-wolf', 'fire', 'middle')} />);
    await waitFor(() => expect(scene.props.appearance.stage).toBe('middle'));
    expect(scene.props.evolution).toBeNull();
    view.rerender(<CompanionPreview variant="primary" creature={syntheticElemental('chick', 'ice', 'grown')} />);
    await waitFor(() => expect(scene.props.appearance.key).toBe('chick-ice-grown'));
    expect(scene.props.evolution).toBeNull();
  });

  it('keeps 2D art and controls while loading; greeting is local and 3D can be disabled', async () => {
    const user = userEvent.setup();
    render(<CompanionPreview creature={pet}><button>Feed using existing controls</button></CompanionPreview>);
    expect(screen.getByRole('img', { name: 'Base Chick' })).toBeInTheDocument();
    expect(scene.props).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Say hello' }));
    expect(screen.getByText(/hello, base chick/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Show 3D view' }));
    await screen.findByTestId('optional-scene');
    expect(screen.getByRole('img', { name: 'Base Chick' })).toBeInTheDocument();
    expect(screen.getByText('Loading the woodland…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Feed using existing controls' })).toBeEnabled();
    act(() => scene.props.onReady());
    expect(screen.queryByRole('img', { name: 'Base Chick' })).toBeNull();
    expect(scene.props.animate).toBe(false);
    await user.click(screen.getByRole('checkbox', { name: 'Animate companion' }));
    expect(scene.props.animate).toBe(true);
    await user.click(screen.getByRole('button', { name: 'Use 2D view' }));
    expect(screen.getByRole('img', { name: 'Base Chick' })).toBeInTheDocument();
    expect(screen.queryByTestId('optional-scene')).toBeNull();
  });

  it('recovers context loss to 2D and retries without disabling the surrounding controls', async () => {
    const user = userEvent.setup();
    render(<CompanionPreview creature={pet}><button>Existing care action</button></CompanionPreview>);
    await user.click(screen.getByRole('button', { name: 'Show 3D view' }));
    await screen.findByTestId('optional-scene');
    act(() => scene.props.onReady());
    act(() => scene.props.onUnavailable());
    expect(screen.getByText(/3d view could not load/i)).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Base Chick' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Existing care action' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Retry 3D view' }));
    await screen.findByTestId('optional-scene');
    expect(screen.getByRole('button', { name: 'Use 2D view' })).toBeInTheDocument();
  });

  it('catches model/renderer errors and retains functional DOM actions', async () => {
    const user = userEvent.setup();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    const consoleWarning = vi.spyOn(console, 'warn').mockImplementation(() => {});
    scene.crash = true;
    render(<CompanionPreview creature={pet}><button>Existing care action</button></CompanionPreview>);
    await user.click(screen.getByRole('button', { name: 'Show 3D view' }));
    await waitFor(() => expect(screen.getByText(/3d view could not load/i)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Existing care action' })).toBeEnabled();
    expect(screen.getByRole('img', { name: 'Base Chick' })).toBeInTheDocument();
    consoleError.mockRestore();
    consoleWarning.mockRestore();
  });

  it('resets greeting and scene state on changed identity and never offers a substituted 3D model', async () => {
    const user = userEvent.setup();
    const view = render(<CompanionPreview creature={pet} />);
    await user.click(screen.getByRole('button', { name: 'Say hello' }));
    view.rerender(<CompanionPreview creature={{ ...pet, id: 2, species: { name: 'Fox', sprite_key: 'fox', icon: '🦊' } }} />);
    expect(screen.queryByText(/hello, base chick/i)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Show 3D view' })).toBeNull();
    expect(screen.getByRole('img', { name: 'Base Fox' })).toBeInTheDocument();
  });

  it('honors the scene kill switch while preserving owned pets and controls', () => {
    vi.stubEnv('VITE_COMPANION_3D', 'false');
    render(<CompanionPreview creature={pet} />);
    expect(screen.queryByRole('button', { name: 'Show 3D view' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Say hello' })).toBeEnabled();
    expect(screen.getByRole('img', { name: 'Base Chick' })).toBeInTheDocument();
  });

  it('requires the stable response species identity before offering a 3D appearance', () => {
    render(<CompanionPreview creature={{ ...pet, species: { ...pet.species, slug: undefined } }} />);
    expect(screen.queryByRole('button', { name: 'Show 3D view' })).toBeNull();
    expect(screen.getByRole('img', { name: 'Base Chick' })).toBeInTheDocument();
    expect(scene.props).toBeNull();
  });
});

describe('Primary companion home', () => {
  it('disables native play controls while animation is explicitly off', async () => {
    const user = userEvent.setup();
    render(<CompanionPreview variant="primary" creature={pet} />);
    await screen.findByTestId('optional-scene');
    act(() => scene.props.onReady());
    await user.click(screen.getByText('View'));
    await user.click(screen.getByRole('checkbox', { name: 'Animate companion' }));
    expect(screen.getByRole('button', { name: 'Hop together' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Look around' })).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: 'Animate companion' }));
    expect(screen.getByRole('button', { name: 'Hop together' })).toBeEnabled();
  });
  it('opens the exact owned 3D companion with idle motion and a direct accessible care action', async () => {
    const user = userEvent.setup();
    const openCare = vi.fn();
    render(<CompanionPreview variant="primary" creature={{ ...pet, name: 'Peep' }} kicker="Your little world" summary="One more favorite snack to evolve." onInteract={openCare}>
      <button>Choose food</button>
    </CompanionPreview>);
    expect(screen.getByRole('heading', { name: 'Peep' })).toBeInTheDocument();
    expect(screen.getByText('Base Chick · Baby · 99/100 growth')).toBeInTheDocument();
    expect(screen.getByText('One more favorite snack to evolve.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Show 3D view' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Say hello' })).toBeEnabled();
    await screen.findByTestId('optional-scene');
    expect(scene.props.appearance.key).toBe('chick');
    expect(scene.props.animate).toBe(true);
    expect(screen.getByRole('button', { name: 'Choose food' })).toBeEnabled();
    act(() => scene.props.onReady());
    expect(screen.queryByText('A little company while you grow.')).toBeNull();
    expect(screen.getByRole('status')).toHaveTextContent('Take a little break with Peep.');
    await user.click(screen.getByRole('button', { name: 'Say hello to Peep' }));
    expect(openCare).toHaveBeenCalledTimes(1);
    expect(scene.props.greeting).toBe(0);
  });

  it('keeps display and motion preferences in a discreet View setting', async () => {
    const user = userEvent.setup();
    render(<CompanionPreview variant="primary" creature={pet} />);
    await screen.findByTestId('optional-scene');
    await user.click(screen.getByText('View'));
    expect(screen.getByRole('button', { name: '3D woodland' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('checkbox', { name: 'Animate companion' })).toBeChecked();
    await user.click(screen.getByRole('checkbox', { name: 'Animate companion' }));
    expect(scene.props.animate).toBe(false);
    await user.click(screen.getByRole('button', { name: '2D portrait' }));
    expect(screen.getByRole('img', { name: 'Base Chick, your companion' })).toBeInTheDocument();
    expect(screen.queryByTestId('optional-scene')).toBeNull();
    expect(screen.getByRole('button', { name: '2D portrait' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: '3D woodland' }));
    await screen.findByTestId('optional-scene');
    expect(scene.props.animate).toBe(false);
  });

  it('recovers a failed primary scene without blocking care and can retry the actual owned appearance', async () => {
    const user = userEvent.setup();
    const openCare = vi.fn();
    render(<CompanionPreview variant="primary" creature={{ ...pet, name: 'Peep', evolved_to_mount: true }} onInteract={openCare} interactionLabel="Explore with Peep">
      <button>Send on an expedition</button>
    </CompanionPreview>);
    await screen.findByTestId('optional-scene');
    expect(scene.props.appearance.key).toBe('bird');
    act(() => scene.props.onUnavailable());
    expect(screen.getByRole('img', { name: 'Peep, your companion' })).toBeInTheDocument();
    expect(screen.getByText(/3d view could not load/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send on an expedition' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Explore with Peep' }));
    expect(openCare).toHaveBeenCalledTimes(1);
    await user.click(screen.getByText('View'));
    await user.click(screen.getByRole('button', { name: 'Retry 3D woodland' }));
    await screen.findByTestId('optional-scene');
    expect(scene.props.appearance.key).toBe('bird');
  });

  it('uses the purchased icon and usable actions for an unsupported species without substituting another creature', () => {
    render(<CompanionPreview variant="primary" creature={{ ...pet, name: 'Juniper', lifecycle_stage: 'middle', species: { name: 'Fox', sprite_key: 'fox', icon: '🦊' } }} onInteract={vi.fn()} />);
    expect(screen.getByRole('heading', { name: 'Juniper' })).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Juniper, your companion' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Say hello to Juniper' })).toBeEnabled();
    expect(screen.getByText('Base Fox · Middle · 99/100 growth')).toBeInTheDocument();
    expect(screen.queryByText('View')).toBeNull();
    expect(scene.props).toBeNull();
  });

  it('honors the kill switch for primary scenes and still permits care', () => {
    vi.stubEnv('VITE_COMPANION_3D', 'false');
    render(<CompanionPreview variant="primary" creature={pet} onInteract={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Say hello to Base Chick' })).toBeEnabled();
    expect(screen.getByRole('img', { name: 'Base Chick, your companion' })).toBeInTheDocument();
    expect(screen.queryByText('View')).toBeNull();
    expect(scene.props).toBeNull();
  });

  it('makes greetings and supplied play local, repeats on tap and resets on identity change', async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const view = render(<CompanionPreview variant="primary" creature={{ ...pet, name: 'Peep' }} />);
    await screen.findByTestId('optional-scene');
    act(() => scene.props.onReady());
    await user.click(screen.getByRole('button', { name: 'Say hello to Peep' }));
    expect(scene.props.interaction).toMatchObject({ action: 'hello', id: 1 });
    expect(screen.getByRole('status')).toHaveTextContent('Peep is happy to see you.');
    await user.click(screen.getByRole('button', { name: 'Hop together' }));
    expect(scene.props.interaction).toMatchObject({ action: 'play', id: 2 });
    await user.click(screen.getByRole('button', { name: 'Look around' }));
    expect(scene.props.interaction.action).toBe('left');
    await user.click(screen.getByRole('button', { name: 'Look around' }));
    expect(scene.props.interaction.action).toBe('right');
    expect(fetchSpy.mock.calls.filter(([, options]) => options?.method && options.method !== 'GET')).toHaveLength(0);
    view.rerender(<CompanionPreview variant="primary" creature={{ ...pet, id: 2, name: 'Pip', evolved_to_mount: true }} />);
    await waitFor(() => expect(scene.props.interaction).toBeNull());
    expect(screen.getByRole('button', { name: 'Fly together' })).toBeDisabled();
    act(() => scene.props.onReady());
    expect(screen.getByRole('button', { name: 'Fly together' })).toBeEnabled();
    fetchSpy.mockRestore();
  });
});
