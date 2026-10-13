import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AvatarPreview from './AvatarPreview';
import { AVATAR_DEFAULTS } from '../../avatar/preferences';
import { resetAvatarAssets } from '../../avatar/modelLoader';

const fixture = vi.hoisted(() => ({ props: null, error: null, missing: false }));
vi.mock('../../avatar/appearance', () => ({ resolveAvatarAppearance: () => fixture.missing ? null : ({
  url: '/synthetic-archer.glb', hairStyle: 'hair-01', textures: { body: '/synthetic-body.png', hair: '/synthetic-hair.png', face: '/synthetic-face.png' },
}) }));
vi.mock('../../avatar/modelLoader', () => ({ resetAvatarAssets: vi.fn() }));
vi.mock('../../avatar/AvatarScene', () => ({ default: (props) => {
  fixture.props = props;
  if (fixture.error) throw fixture.error;
  return <div data-testid="avatar-scene" />;
} }));
beforeEach(() => { fixture.props = null; fixture.error = null; fixture.missing = false; resetAvatarAssets.mockClear(); });

describe('AvatarPreview', () => {
  it('starts the avatar without an opt-in and keeps an accessible loading state', async () => {
    render(<AvatarPreview preferences={AVATAR_DEFAULTS} />);
    expect(screen.getByRole('img', { name: 'Your Archer character' })).toBeInTheDocument();
    expect(screen.getByText('Loading your character…')).toBeInTheDocument();
    await screen.findByTestId('avatar-scene');
    act(() => fixture.props.onReady());
    expect(screen.queryByText('Loading your character…')).toBeNull();
  });

  it('recovers WebGL loss and retries while retaining surrounding customization', async () => {
    const user = userEvent.setup();
    render(<><AvatarPreview preferences={AVATAR_DEFAULTS} /><button>Customize character</button></>);
    await screen.findByTestId('avatar-scene');
    act(() => fixture.props.onUnavailable());
    expect(screen.getByText(/preview is unavailable/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Customize character' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Retry character preview' }));
    await screen.findByTestId('avatar-scene');
    expect(resetAvatarAssets).toHaveBeenCalledWith(expect.any(Object), []);
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
