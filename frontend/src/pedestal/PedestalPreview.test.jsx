import { StrictMode } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PedestalPreview from './PedestalPreview';

const fixture = vi.hoisted(() => ({ props: null, missing: false, motionAllowed: true, error: null, mounts: 0, unmounts: 0 }));
vi.mock('./pedestalRelease', () => ({ stagedPedestalRelease: () => fixture.missing ? null : ({ manifestUrl: '/synthetic-manifest.json', manifestSha256: 'a'.repeat(64) }) }));
vi.mock('../companion/useSceneMotionAllowed', () => ({ default: () => fixture.motionAllowed }));
vi.mock('./PedestalScene', async () => {
  const { useEffect } = await import('react');
  return { default: function MockScene(props) {
    fixture.props = props;
    useEffect(() => { fixture.mounts += 1; return () => { fixture.unmounts += 1; }; }, []);
    if (fixture.error) throw fixture.error;
    return <canvas data-testid="pedestal-scene" />;
  } };
});

beforeEach(() => { fixture.props = null; fixture.missing = false; fixture.motionAllowed = true; fixture.error = null; fixture.mounts = 0; fixture.unmounts = 0; });

describe('decorative pedestal preview', () => {
  it('announces loading and ready state without implying account ownership', async () => {
    render(<PedestalPreview />);
    expect(screen.getByRole('img', { name: 'Decorative egg on a woodland pedestal' })).toBeInTheDocument();
    const display = screen.getByRole('group', { name: 'Woodland display' });
    expect(display).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('status')).toHaveTextContent('Loading the woodland display…');
    await screen.findByTestId('pedestal-scene');
    expect(fixture.props.eggAssetId).toBe('normal-egg');
    act(() => fixture.props.onReady());
    expect(display).toHaveAttribute('data-display-state', 'ready');
    expect(display).toHaveAttribute('aria-busy', 'false');
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('keeps a DOM display toggle usable before loading and releases/remounts the optional renderer', async () => {
    const user = userEvent.setup();
    render(<PedestalPreview />);
    await screen.findByTestId('pedestal-scene');
    act(() => fixture.props.onReady());
    await user.click(screen.getByRole('button', { name: 'Turn off 3D display' }));
    expect(screen.queryByTestId('pedestal-scene')).toBeNull();
    expect(fixture.unmounts).toBe(1);
    expect(screen.getByRole('status')).toHaveTextContent('3D display is off.');
    expect(screen.getByRole('button', { name: 'Turn on 3D display' })).toHaveAttribute('aria-pressed', 'false');
    await user.click(screen.getByRole('button', { name: 'Turn on 3D display' }));
    await screen.findByTestId('pedestal-scene');
    expect(fixture.mounts).toBe(2);
    expect(screen.getByRole('group')).toHaveAttribute('data-display-state', 'loading');
  });

  it('pauses reduced, offscreen and background motion while preserving the selected native take', async () => {
    fixture.motionAllowed = false;
    const view = render(<PedestalPreview eggAssetId="legendary-egg-hatching-soon" />);
    await screen.findByTestId('pedestal-scene');
    expect(fixture.props.motionAllowed).toBe(false);
    act(() => fixture.props.onReady());
    expect(screen.getByText('Animations are paused.')).toBeInTheDocument();
    fixture.motionAllowed = true;
    view.rerender(<PedestalPreview eggAssetId="legendary-egg-hatching-soon" />);
    expect(fixture.props.motionAllowed).toBe(true);
    expect(fixture.props.eggAssetId).toBe('legendary-egg-hatching-soon');
    view.rerender(<PedestalPreview eggAssetId="legendary-egg-hatching-soon" animate={false} />);
    expect(fixture.props.motionAllowed).toBe(false);
    expect(fixture.mounts).toBe(1);
  });

  it('resets loading for a new native rig without reusing the previous take', async () => {
    const view = render(<PedestalPreview eggAssetId="normal-egg" />);
    await screen.findByTestId('pedestal-scene');
    act(() => fixture.props.onReady());
    view.rerender(<PedestalPreview eggAssetId="legendary-egg-idle-wobble" />);
    await waitFor(() => expect(fixture.props.eggAssetId).toBe('legendary-egg-idle-wobble'));
    expect(screen.getByRole('group')).toHaveAttribute('data-display-state', 'loading');
    expect(fixture.unmounts).toBe(1);
  });

  it('recovers model or WebGL failures with a fresh lazy renderer while DOM controls remain usable', async () => {
    const user = userEvent.setup();
    render(<><PedestalPreview /><button>Existing action</button></>);
    await screen.findByTestId('pedestal-scene');
    act(() => fixture.props.onUnavailable());
    expect(screen.getByRole('status')).toHaveTextContent('The decorative 3D display is unavailable.');
    expect(screen.getByRole('button', { name: 'Existing action' })).toBeEnabled();
    expect(screen.queryByTestId('pedestal-scene')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Retry 3D display' }));
    await screen.findByTestId('pedestal-scene');
    expect(screen.getByRole('group')).toHaveAttribute('data-display-state', 'loading');
    act(() => fixture.props.onReady());
    expect(screen.getByRole('group')).toHaveAttribute('data-display-state', 'ready');
  });

  it('contains lazy-renderer errors and retries a failed module without replacing the page', async () => {
    const user = userEvent.setup();
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    fixture.error = new Error('Synthetic module failure');
    render(<PedestalPreview />);
    await screen.findByRole('button', { name: 'Retry 3D display' });
    fixture.error = null;
    await user.click(screen.getByRole('button', { name: 'Retry 3D display' }));
    await screen.findByTestId('pedestal-scene');
    consoleError.mockRestore();
  });

  it.each([null, 'unknown-egg'])('does not invent a private build or catalog identity when unavailable: %s', (eggAssetId) => {
    fixture.missing = eggAssetId === null;
    render(<PedestalPreview eggAssetId={eggAssetId} />);
    expect(screen.getByRole('status')).toHaveTextContent('The decorative 3D display is unavailable.');
    expect(screen.queryByTestId('pedestal-scene')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Retry 3D display' })).toBeNull();
  });

  it('supports a pedestal-only composition and retains layout props through StrictMode', async () => {
    const view = render(<StrictMode><PedestalPreview eggAssetId={null} stageClassName="h-48 sm:h-80" className="mt-3" /></StrictMode>);
    await screen.findByTestId('pedestal-scene');
    expect(screen.getByRole('img', { name: 'Decorative woodland pedestal' })).toBeInTheDocument();
    expect(screen.getByRole('group')).toHaveClass('h-48', 'sm:h-80');
    expect(screen.getByRole('group').parentElement).toHaveClass('mt-3');
    expect(fixture.props.eggAssetId).toBeNull();
    view.unmount();
    expect(fixture.mounts).toBe(fixture.unmounts);
  });
});
