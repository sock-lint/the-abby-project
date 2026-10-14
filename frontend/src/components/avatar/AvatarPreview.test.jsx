import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AvatarPreview from './AvatarPreview';
import { AVATAR_DEFAULTS } from '../../avatar/preferences';
import { resetAvatarAssets } from '../../avatar/modelLoader';
import { resolveAvatarAppearance } from '../../avatar/appearance';

const fixture = vi.hoisted(() => ({ props: null, error: null, missing: false, motionAllowed: true }));
const archerDefinition = { id: 'female-archer', label: 'Female Archer', renderer_adapter: 'female-archer' };
const configuration = {
  avatar_id: 'female-archer',
  appearance: Object.fromEntries(Object.entries(AVATAR_DEFAULTS).filter(([key]) => !['headwear_style', 'mask_style', 'bow_style', 'quiver_style'].includes(key))),
  accessories: { headwear: 'none', face_accessory: 'none', left_hand: 'none', right_hand: 'none', back: 'none' },
};
vi.mock('../../companion/useSceneMotionAllowed', () => ({ default: () => fixture.motionAllowed }));
vi.mock('../../avatar/appearance', () => ({ resolveAvatarAppearance: vi.fn((preferences) => fixture.missing ? null : ({
  url: preferences.outfit_style === 'archer-02' ? '/synthetic-archer-02.glb' : '/synthetic-archer.glb',
  hairStyle: 'hair-01', wardrobe: { headwear: preferences.headwear_style, mask: preferences.mask_style, bow: preferences.bow_style, quiver: preferences.quiver_style },
  textures: { body: '/synthetic-body.png', hair: '/synthetic-hair.png', face: '/synthetic-face.png' },
})) }));
vi.mock('../../avatar/modelLoader', () => ({ resetAvatarAssets: vi.fn() }));
vi.mock('../../avatar/AvatarScene', () => ({ default: (props) => {
  fixture.props = props;
  if (fixture.error) throw fixture.error;
  return <canvas data-testid="avatar-scene" />;
} }));
beforeEach(() => { fixture.props = null; fixture.error = null; fixture.missing = false; fixture.motionAllowed = true; resetAvatarAssets.mockClear(); resolveAvatarAppearance.mockClear(); });

function pointer(type, target, { id = 1, x = 20, y = 20, button = 0, primary = true, pointerType = 'touch' } = {}) {
  // jsdom does not supply PointerEvent, but React receives the same browser
  // pointer fields from this bubbling event as it does from the real canvas.
  const event = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y, button });
  Object.assign(event, { pointerId: id, pointerType, isPrimary: primary });
  fireEvent(target, event);
}

async function readyPreview() {
  render(<AvatarPreview preferences={AVATAR_DEFAULTS} />);
  const canvas = await screen.findByTestId('avatar-scene');
  act(() => fixture.props.onReady());
  return canvas;
}

describe('AvatarPreview', () => {
  it('renders a valid generic configuration through the registered Archer boundary', async () => {
    render(<AvatarPreview configuration={configuration} avatarDefinition={archerDefinition} />);
    await screen.findByTestId('avatar-scene');
    expect(resolveAvatarAppearance).toHaveBeenCalledWith(AVATAR_DEFAULTS);
    expect(screen.getByRole('img', { name: 'Your Female Archer avatar' })).toBeInTheDocument();
  });

  it.each([
    ['missing configuration', null, archerDefinition],
    ['invalid appearance', { ...configuration, appearance: { ...configuration.appearance, outfit_style: 'synthetic-knight' } }, archerDefinition],
    ['unsupported right hand', { ...configuration, accessories: { ...configuration.accessories, right_hand: 'synthetic-sword' } }, archerDefinition],
    ['missing catalog definition', configuration, undefined],
  ])('does not substitute default Archer for %s', (name, value, definition) => {
    render(<AvatarPreview preferences={AVATAR_DEFAULTS} configuration={value} avatarDefinition={definition} />);
    expect(screen.getByText('The avatar preview is unavailable. You can still customize your look.')).toBeInTheDocument();
    if (!definition) expect(screen.getByRole('img', { name: 'Your avatar' })).toBeInTheDocument();
    expect(screen.queryByTestId('avatar-scene')).toBeNull();
    expect(resolveAvatarAppearance).not.toHaveBeenCalled();
  });

  it('uses the registered renderer with the selected avatar label', async () => {
    render(<AvatarPreview preferences={AVATAR_DEFAULTS} avatarDefinition={{ id: 'female-archer', label: 'Female Archer', renderer_adapter: 'female-archer' }} />);
    expect(screen.getByRole('img', { name: 'Your Female Archer avatar' })).toBeInTheDocument();
    expect(screen.getByText('Loading your avatar…')).toBeInTheDocument();
    await screen.findByTestId('avatar-scene');
    expect(resolveAvatarAppearance).toHaveBeenCalledWith(AVATAR_DEFAULTS);
    act(() => fixture.props.onReady());
    expect(screen.getByRole('button', { name: 'Play animation' })).toBeEnabled();
  });

  it.each(['synthetic-knight', undefined, 'female-archer'])('never substitutes Archer for an unknown avatar using renderer %s', async (adapter) => {
    const { rerender } = render(<AvatarPreview preferences={AVATAR_DEFAULTS} />);
    await screen.findByTestId('avatar-scene');
    act(() => fixture.props.onReady());
    resolveAvatarAppearance.mockClear();
    rerender(<AvatarPreview preferences={AVATAR_DEFAULTS} avatarDefinition={{ id: 'synthetic-knight', label: 'Knight', renderer_adapter: adapter }} />);
    expect(screen.getByRole('img', { name: 'Your Knight avatar' })).toBeInTheDocument();
    expect(screen.getByText('The avatar preview is unavailable. You can still customize your look.')).toBeInTheDocument();
    expect(screen.queryByTestId('avatar-scene')).toBeNull();
    expect(resolveAvatarAppearance).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Play animation' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Retry avatar preview' })).toBeNull();
  });

  it('accepts compact stage sizing without resetting ready state or camera and tap controls', async () => {
    const user = userEvent.setup();
    const definition = { id: 'female-archer', label: 'Female Archer', renderer_adapter: 'female-archer' };
    const { rerender } = render(<AvatarPreview preferences={AVATAR_DEFAULTS} avatarDefinition={definition} className="sticky top-0" stageClassName="h-48 sm:h-80" compact />);
    const canvas = await screen.findByTestId('avatar-scene');
    act(() => fixture.props.onReady());
    const view = screen.getByRole('group', { name: 'Character view' });
    expect(view).toHaveClass('h-48', 'sm:h-80');
    expect(view).not.toHaveClass('h-80');
    expect(view.parentElement).toHaveClass('sticky', 'top-0');
    const help = screen.getByText(/Tap for an animation/);
    expect(help).toHaveClass('sr-only');
    expect(view).toHaveAttribute('aria-describedby', help.id);
    expect(screen.queryByRole('button', { name: 'Play animation' })).toBeNull();
    const reset = screen.getByRole('button', { name: 'Reset view' });
    expect(view).toContainElement(reset);
    pointer('pointerdown', canvas);
    pointer('pointerup', canvas);
    fireEvent.keyDown(view, { key: 'ArrowLeft' });
    expect(fixture.props.interaction.id).toBe(1);
    expect(fixture.props.cameraOrbit).toEqual({ id: 1, horizontal: 1, vertical: 0 });
    rerender(<AvatarPreview preferences={AVATAR_DEFAULTS} avatarDefinition={definition} className="sticky top-2" stageClassName="h-56 sm:h-80" compact />);
    expect(view).toHaveClass('h-56', 'sm:h-80');
    expect(view).not.toHaveClass('h-48');
    expect(view).toHaveAttribute('aria-busy', 'false');
    expect(fixture.props.interaction.id).toBe(1);
    expect(fixture.props.cameraOrbit.id).toBe(1);
    pointer('pointerdown', canvas);
    pointer('pointerup', canvas);
    expect(fixture.props.interaction).toEqual({ id: 2, action: 'twirl' });
    fireEvent.keyDown(view, { key: 'Home' });
    expect(fixture.props.cameraReset).toBe(1);
    pointer('pointerdown', reset);
    pointer('pointerup', reset);
    fireEvent.click(reset);
    expect(fixture.props.cameraReset).toBe(2);
    expect(fixture.props.interaction.id).toBe(2);
    reset.focus();
    await user.keyboard('{Enter}{ArrowRight} ');
    expect(fixture.props.cameraReset).toBe(4);
    expect(fixture.props.interaction.id).toBe(2);
    expect(fixture.props.cameraOrbit).toEqual({ id: 1, horizontal: 1, vertical: 0 });
  });

  it('resets loading and local playback when wardrobe choices share the same texture atlas', async () => {
    const { rerender } = render(<AvatarPreview preferences={{ ...AVATAR_DEFAULTS, bow_style: 'bow-myth' }} />);
    const canvas = await screen.findByTestId('avatar-scene');
    act(() => fixture.props.onReady());
    pointer('pointerdown', canvas);
    pointer('pointerup', canvas);
    expect(fixture.props.interaction.id).toBe(1);
    rerender(<AvatarPreview preferences={{ ...AVATAR_DEFAULTS, bow_style: 'bow-vines' }} />);
    await waitFor(() => expect(fixture.props.appearance.wardrobe.bow).toBe('bow-vines'));
    expect(screen.getByRole('group', { name: 'Character view' })).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('button', { name: 'Play animation' })).toBeDisabled();
    expect(fixture.props.interaction).toEqual({ id: 0, action: null });
    act(() => fixture.props.onReady());
    expect(screen.getByRole('group', { name: 'Character view' })).toHaveAttribute('aria-busy', 'false');
  });

  it('starts a new outfit rig with a fresh loading state and cleared local interaction', async () => {
    const { rerender } = render(<AvatarPreview preferences={AVATAR_DEFAULTS} />);
    const canvas = await screen.findByTestId('avatar-scene');
    act(() => fixture.props.onReady());
    pointer('pointerdown', canvas);
    pointer('pointerup', canvas);
    expect(fixture.props.interaction.id).toBe(1);
    rerender(<AvatarPreview preferences={{ ...AVATAR_DEFAULTS, outfit_style: 'archer-02' }} />);
    await waitFor(() => expect(fixture.props.appearance.url).toBe('/synthetic-archer-02.glb'));
    expect(screen.getByText('Loading your character…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Play animation' })).toBeDisabled();
    expect(fixture.props.interaction).toEqual({ id: 0, action: null });
    act(() => fixture.props.onReady());
    expect(screen.queryByText('Loading your character…')).toBeNull();
  });

  it('starts the character without an opt-in and keeps an accessible loading state', async () => {
    render(<AvatarPreview preferences={AVATAR_DEFAULTS} />);
    expect(screen.getByRole('img', { name: 'Your Archer character' })).toBeInTheDocument();
    expect(screen.getByText('Loading your character…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Play animation' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reset view' })).toBeDisabled();
    expect(screen.getByRole('group', { name: 'Character view' })).toHaveAttribute('tabindex', '-1');
    await screen.findByTestId('avatar-scene');
    act(() => fixture.props.onReady());
    expect(screen.queryByText('Loading your character…')).toBeNull();
    expect(screen.getByRole('button', { name: 'Play animation' })).toBeEnabled();
    expect(screen.getByRole('group', { name: 'Character view' })).toHaveAttribute('tabindex', '0');
  });

  it('cycles different local reactions from touch taps and mouse clicks on the actual canvas', async () => {
    const canvas = await readyPreview();
    for (const [index, action] of ['hop', 'twirl', 'bow', 'hop'].entries()) {
      pointer('pointerdown', canvas, { pointerType: index % 2 ? 'mouse' : 'touch' });
      pointer('pointermove', canvas, { x: 24, y: 23 });
      pointer('pointerup', canvas, { x: 24, y: 23 });
      expect(fixture.props.interaction).toEqual({ id: index + 1, action });
    }
    expect(fixture.props.cameraReset).toBe(0);
  });

  it('keeps dragging separate from tapping even when the pointer returns to where it began', async () => {
    const canvas = await readyPreview();
    pointer('pointerdown', canvas);
    pointer('pointermove', canvas, { x: 80, y: 45 });
    pointer('pointermove', canvas);
    pointer('pointerup', canvas);
    expect(fixture.props.interaction).toEqual({ id: 0, action: null });

    // A final position beyond the tap allowance also rejects sparse gestures
    // where the browser has not delivered a move event.
    pointer('pointerdown', canvas);
    pointer('pointerup', canvas, { x: 40 });
    expect(fixture.props.interaction.id).toBe(0);
  });

  it.each(['pointercancel', 'lostpointercapture'])('never plays a reaction after %s', async (cancelType) => {
    const canvas = await readyPreview();
    pointer('pointerdown', canvas);
    pointer(cancelType, canvas);
    pointer('pointerup', canvas);
    expect(fixture.props.interaction.id).toBe(0);

    pointer('pointerdown', canvas);
    pointer('pointerup', canvas);
    expect(fixture.props.interaction).toEqual({ id: 1, action: 'hop' });
  });

  it('does not treat multiple fingers or secondary mouse buttons as a tap', async () => {
    const canvas = await readyPreview();
    pointer('pointerdown', canvas);
    pointer('pointerdown', canvas, { id: 2, primary: false });
    pointer('pointerup', canvas, { id: 2, primary: false });
    pointer('pointerup', canvas);
    pointer('pointerdown', canvas, { button: 2, pointerType: 'mouse' });
    pointer('pointerup', canvas, { button: 2, pointerType: 'mouse' });
    expect(fixture.props.interaction.id).toBe(0);
  });

  it('provides keyboard animation and camera controls with a separate reset', async () => {
    const user = userEvent.setup();
    await readyPreview();
    const play = screen.getByRole('button', { name: 'Play animation' });
    play.focus();
    await user.keyboard('{Enter}');
    expect(fixture.props.interaction).toEqual({ id: 1, action: 'hop' });
    await user.keyboard(' ');
    expect(fixture.props.interaction).toEqual({ id: 2, action: 'twirl' });

    const view = screen.getByRole('group', { name: 'Character view' });
    view.focus();
    for (const [index, [key, horizontal, vertical]] of [
      ['ArrowLeft', 1, 0], ['ArrowUp', 0, 1], ['ArrowRight', -1, 0], ['ArrowDown', 0, -1],
    ].entries()) {
      await user.keyboard(`{${key}}`);
      expect(fixture.props.cameraOrbit).toEqual({ id: index + 1, horizontal, vertical });
    }
    expect(fixture.props.interaction.id).toBe(2);
    await user.keyboard('{Enter}');
    expect(fixture.props.interaction).toEqual({ id: 3, action: 'bow' });
    await user.keyboard(' ');
    expect(fixture.props.interaction).toEqual({ id: 4, action: 'hop' });
    fireEvent.keyDown(view, { key: 'Enter', repeat: true });
    expect(fixture.props.interaction.id).toBe(4);
    await user.keyboard('{Home}');
    expect(fixture.props.cameraReset).toBe(1);
    await user.click(screen.getByRole('button', { name: 'Reset view' }));
    expect(fixture.props.cameraReset).toBe(2);
    expect(fixture.props.interaction.id).toBe(4);
  });

  it('pauses reactions with motion preferences while keeping direct camera controls available', async () => {
    const user = userEvent.setup();
    fixture.motionAllowed = false;
    const canvas = await readyPreview();
    expect(fixture.props.motionAllowed).toBe(false);
    expect(screen.getByRole('button', { name: 'Play animation' })).toBeDisabled();
    expect(screen.getByText(/Animations are paused/)).toBeInTheDocument();
    pointer('pointerdown', canvas);
    pointer('pointerup', canvas);
    const view = screen.getByRole('group', { name: 'Character view' });
    view.focus();
    await user.keyboard('{Enter}{ArrowLeft}');
    expect(fixture.props.interaction.id).toBe(0);
    expect(fixture.props.cameraOrbit).toEqual({ id: 1, horizontal: 1, vertical: 0 });
    await user.click(screen.getByRole('button', { name: 'Reset view' }));
    expect(fixture.props.cameraReset).toBe(1);
  });

  it('recovers WebGL loss and retries while retaining surrounding customization', async () => {
    const user = userEvent.setup();
    render(<><AvatarPreview preferences={AVATAR_DEFAULTS} /><button>Customize character</button></>);
    const canvas = await screen.findByTestId('avatar-scene');
    act(() => fixture.props.onReady());
    pointer('pointerdown', canvas);
    pointer('pointerup', canvas);
    expect(fixture.props.interaction.id).toBe(1);
    act(() => fixture.props.onUnavailable());
    expect(screen.getByText(/preview is unavailable/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Customize character' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Retry character preview' }));
    await screen.findByTestId('avatar-scene');
    expect(resetAvatarAssets).toHaveBeenCalledWith(expect.any(Object), []);
    expect(fixture.props.interaction).toEqual({ id: 0, action: null });
    expect(fixture.props.cameraReset).toBe(0);
    expect(screen.getByRole('button', { name: 'Play animation' })).toBeDisabled();
  });

  it('retries a failed supplied texture without treating the preview as saved appearance', async () => {
    const user = userEvent.setup();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    fixture.error = new Error('Could not load /synthetic-hair.png');
    render(<AvatarPreview preferences={AVATAR_DEFAULTS} />);
    await waitFor(() => expect(screen.getByText(/preview is unavailable/)).toBeInTheDocument());
    fixture.error = null;
    await user.click(screen.getByRole('button', { name: 'Retry character preview' }));
    await screen.findByTestId('avatar-scene');
    expect(resetAvatarAssets).toHaveBeenCalledWith(expect.any(Object), ['/synthetic-hair.png']);
    consoleError.mockRestore();
  });

  it('does not pretend the 3D asset exists when the private build inputs are absent', () => {
    fixture.missing = true;
    render(<AvatarPreview preferences={AVATAR_DEFAULTS} />);
    expect(screen.getByText(/preview is unavailable/)).toBeInTheDocument();
    expect(screen.queryByTestId('avatar-scene')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Retry character preview' })).toBeNull();
  });
});
