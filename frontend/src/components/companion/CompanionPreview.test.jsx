import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CompanionPreview from './CompanionPreview';

const scene = vi.hoisted(() => ({ props: null, crash: false }));
vi.mock('../../companion/appearance', async () => {
  const actual = await vi.importActual('../../companion/appearance');
  return { ...actual, resolveAppearance: (creature) => creature?.species?.sprite_key === 'cute-chick' && creature.potion?.slug === 'base'
    ? { key: 'chick', url: '/test-chick.glb' } : null };
});
vi.mock('../../companion/modelLoader', () => ({ resetModels: vi.fn() }));
vi.mock('../../companion/CompanionScene', () => ({ default: (props) => {
  scene.props = props;
  if (scene.crash) throw new Error('Synthetic model load failure');
  return <div data-testid="optional-scene" />;
} }));

const pet = { id: 1, species: { name: 'Chick', sprite_key: 'cute-chick', icon: '🐤' }, potion: { name: 'Base', slug: 'base' }, growth_points: 99, evolved_to_mount: false };
beforeEach(() => { scene.props = null; scene.crash = false; vi.unstubAllEnvs(); });

describe('Optional companion preview', () => {
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
});
