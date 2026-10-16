import { selectDropdown, openDropdown } from '../../test/selectDropdown';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CompanionPreview from './CompanionPreview';

const scene = vi.hoisted(() => ({ props: null }));
const actions = {
  chick: ['bite-attack', 'cast-spell', 'die', 'idle', 'jump-forward-in-place', 'jump-forward-w-root', 'take-damage', 'turn-left', 'turn-right'],
  fledgling: ['bite-attack', 'cast-spell', 'die', 'idle-02', 'idle', 'run-forward-in-place', 'run-forward-w-root', 'take-damage', 'turn-left', 'turn-right', 'walk-forward-in-place', 'walk-forward-w-root'],
  bird: ['bite-attack', 'cast-spell', 'die', 'fly-forward-in-place', 'fly-forward-w-root', 'idle', 'projectile-attack', 'take-damage', 'turn-left', 'turn-right'],
};

vi.mock('../../companion/appearance', () => ({
  creatureLabel: (creature) => `Base ${creature.species.name}`,
  resolveAppearance: (creature) => ({
    key: creature.evolution_stage,
    pipeline: 'abby-assets-bird',
    url: `/${creature.evolution_stage}.glb`,
    motions: actions[creature.evolution_stage].map((action) => ({
      id: `source-${action}`, action, label: action, loop: action.includes('idle') || action.includes('forward'),
    })),
  }),
}));
vi.mock('../../companion/CompanionScene', () => ({ default: (props) => {
  scene.props = props;
  return <span data-testid="bird-scene" />;
} }));

const pet = { id: 1, species: { name: 'Chick', slug: 'chick', sprite_key: 'cute-chick', icon: '🐤' }, potion: { name: 'Base', slug: 'base' }, growth_points: 0, evolved_to_mount: false, evolution_stage: 'chick' };
beforeEach(() => { scene.props = null; });

describe('Bird Evolution companion controls', () => {
  it('offers all 31 supplied motions only for their current owned stage, with repeatable local playback and rest', async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, 'fetch');
    const view = render(<CompanionPreview variant="primary" creature={pet} />);
    let count = 0;
    for (const [stage, stageActions] of Object.entries(actions)) {
      view.rerender(<CompanionPreview variant="primary" creature={{ ...pet, evolution_stage: stage, evolved_to_mount: stage === 'bird' }} />);
      await screen.findByTestId('bird-scene');
      act(() => scene.props.onReady());
      await user.click(screen.getByText('More motions'));
      const picker = screen.getByRole('combobox', { name: 'Companion motion' });
      const motions = await openDropdown(user, picker);
      expect(motions.getAllByRole('option').map((option) => option.getAttribute('data-value'))).toEqual(stageActions.map((action) => `source-${action}`));
      for (const action of stageActions) {
        await selectDropdown(user, picker, `source-${action}`);
        await user.click(screen.getByRole('button', { name: 'Play motion' }));
        expect(scene.props.interaction).toMatchObject({ action: `source-${action}` });
        count += 1;
      }
      const previousId = scene.props.interaction.id;
      await user.click(screen.getByRole('button', { name: 'Play motion' }));
      expect(scene.props.interaction.id).toBeGreaterThan(previousId);
      await user.click(screen.getByRole('button', { name: 'Return to rest' }));
      expect(scene.props.interaction).toMatchObject({ action: 'idle' });
    }
    expect(count).toBe(31);
    expect(fetchSpy.mock.calls.filter(([, options]) => options?.method && options.method !== 'GET')).toHaveLength(0);
    fetchSpy.mockRestore();
  });

  it('plays each server-confirmed evolution once, preserves view preferences, and fences an old ready callback', async () => {
    const user = userEvent.setup();
    const view = render(<CompanionPreview creature={pet} />);
    await user.click(screen.getByRole('button', { name: 'Show 3D view' }));
    await screen.findByTestId('bird-scene');
    expect(scene.props.evolution).toBeNull();
    const oldReady = scene.props.onReady;
    act(() => oldReady());
    const fledgling = { ...pet, growth_points: 50, evolution_stage: 'fledgling' };
    view.rerender(<CompanionPreview creature={fledgling} />);
    await screen.findByTestId('bird-scene');
    expect(scene.props.evolution).toMatchObject({ from: 'chick', to: 'fledgling' });
    const firstReceipt = scene.props.evolution.id;
    expect(screen.getByText('Loading the woodland…')).toBeInTheDocument();
    act(() => oldReady());
    expect(screen.getByText('Loading the woodland…')).toBeInTheDocument();
    act(() => scene.props.onReady());
    view.rerender(<CompanionPreview creature={{ ...fledgling, growth_points: 65 }} />);
    expect(scene.props.evolution.id).toBe(firstReceipt);
    view.rerender(<CompanionPreview creature={{ ...fledgling, growth_points: 100, evolved_to_mount: true, evolution_stage: 'bird' }} />);
    await screen.findByTestId('bird-scene');
    expect(scene.props.evolution).toMatchObject({ from: 'fledgling', to: 'bird' });
    expect(scene.props.evolution.id).toBeGreaterThan(firstReceipt);
  });

  it('loads a persisted stage at idle without replaying evolution and clears pending evolution on identity change', async () => {
    const view = render(<CompanionPreview variant="primary" creature={{ ...pet, evolution_stage: 'fledgling', growth_points: 65 }} />);
    await screen.findByTestId('bird-scene');
    expect(scene.props.evolution).toBeNull();
    expect(screen.getByText('Fledgling · 65/100 growth')).toBeInTheDocument();
    view.rerender(<CompanionPreview variant="primary" creature={{ ...pet, evolution_stage: 'bird', evolved_to_mount: true }} />);
    await screen.findByTestId('bird-scene');
    expect(scene.props.evolution).toMatchObject({ from: 'fledgling', to: 'bird' });
    view.rerender(<CompanionPreview variant="primary" creature={{ ...pet, id: 2, evolution_stage: 'bird', evolved_to_mount: true }} />);
    await screen.findByTestId('bird-scene');
    expect(scene.props.evolution).toBeNull();
  });

  it('keeps 2D preference across growth and reports availability for the existing fallback ceremony', async () => {
    const user = userEvent.setup();
    const onPresentationChange = vi.fn();
    const view = render(<CompanionPreview variant="primary" creature={pet} onPresentationChange={onPresentationChange} />);
    await screen.findByTestId('bird-scene');
    act(() => scene.props.onReady());
    expect(onPresentationChange).toHaveBeenLastCalledWith({ creatureId: 1, sharedBirdReady: true, evolutionMotionEnabled: true });
    await user.click(screen.getByText('View'));
    await user.click(screen.getByRole('button', { name: '2D portrait' }));
    expect(onPresentationChange).toHaveBeenLastCalledWith({ creatureId: 1, sharedBirdReady: false, evolutionMotionEnabled: true });
    view.rerender(<CompanionPreview variant="primary" creature={{ ...pet, growth_points: 50, evolution_stage: 'fledgling' }} onPresentationChange={onPresentationChange} />);
    expect(screen.queryByTestId('bird-scene')).toBeNull();
    await user.click(screen.getByText('View'));
    await user.click(screen.getByRole('button', { name: '3D woodland' }));
    await screen.findByTestId('bird-scene');
    expect(scene.props.evolution).toBeNull();
  });

  it('resets a scene to destination idle and ignores callbacks belonging to the disposed attempt', async () => {
    const user = userEvent.setup();
    const view = render(<CompanionPreview creature={pet} />);
    await user.click(screen.getByRole('button', { name: 'Show 3D view' }));
    await screen.findByTestId('bird-scene');
    act(() => scene.props.onReady());
    view.rerender(<CompanionPreview creature={{ ...pet, growth_points: 50, evolution_stage: 'fledgling' }} />);
    await screen.findByTestId('bird-scene');
    const old = scene.props;
    act(() => old.onReady());
    await user.click(screen.getByRole('button', { name: 'Reset companion view' }));
    await screen.findByTestId('bird-scene');
    expect(scene.props.evolution).toBeNull();
    act(() => { old.onReady(); old.onUnavailable(); old.onPlaybackState({ status: 'playing', variantId: 'source-die', stage: 'fledgling' }); });
    expect(screen.getByText('Loading the woodland…')).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Companion playback' })).toHaveAttribute('data-playback-status', 'loading');
    expect(screen.queryByText(/3d view could not load/i)).toBeNull();
    act(() => scene.props.onReady());
    expect(screen.queryByText('Loading the woodland…')).toBeNull();
  });

  it('keeps model readiness separate from the view setting and live reduced-motion preference', async () => {
    let reduced = false;
    const listeners = new Set();
    const media = { get matches() { return reduced; },
      addEventListener: (_event, listener) => listeners.add(listener),
      removeEventListener: (_event, listener) => listeners.delete(listener),
    };
    const matchMedia = vi.spyOn(window, 'matchMedia').mockReturnValue(media);
    try {
      const user = userEvent.setup();
      const onPresentationChange = vi.fn();
      const view = render(<CompanionPreview variant="primary" creature={pet} onPresentationChange={onPresentationChange} />);
      await screen.findByTestId('bird-scene');
      act(() => scene.props.onReady());
      await user.click(screen.getByText('View'));
      await user.click(screen.getByRole('checkbox', { name: 'Animate companion' }));
      expect(onPresentationChange).toHaveBeenLastCalledWith({ creatureId: 1, sharedBirdReady: true, evolutionMotionEnabled: false });
      await user.click(screen.getByRole('checkbox', { name: 'Animate companion' }));
      expect(onPresentationChange).toHaveBeenLastCalledWith({ creatureId: 1, sharedBirdReady: true, evolutionMotionEnabled: true });
      act(() => { reduced = true; listeners.forEach((listener) => listener()); });
      expect(onPresentationChange).toHaveBeenLastCalledWith({ creatureId: 1, sharedBirdReady: true, evolutionMotionEnabled: false });
      expect(screen.getByTestId('bird-scene')).toBeInTheDocument();
      view.unmount();
      expect(listeners.size).toBe(0);
    } finally { matchMedia.mockRestore(); }
  });
});
