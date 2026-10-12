import { useRef } from 'react';
import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import useSceneMotionAllowed from './useSceneMotionAllowed';

let observers;
let media;
let hidden;

function Scene({ tabHidden = false }) {
  const ref = useRef(null);
  const allowed = useSceneMotionAllowed(ref);
  return <div hidden={tabHidden}><div ref={ref} data-testid="scene" data-animated={allowed} /></div>;
}

function intersection(visible) {
  act(() => observers[0].callback([{ target: screen.getByTestId('scene'), isIntersecting: visible }]));
}

beforeEach(() => {
  observers = [];
  hidden = false;
  media = { matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() };
  vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
  vi.spyOn(window, 'matchMedia').mockReturnValue(media);
  vi.stubGlobal('IntersectionObserver', class {
    constructor(callback) { this.callback = callback; this.observe = vi.fn(); this.disconnect = vi.fn(); observers.push(this); }
  });
});

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe('scene motion visibility', () => {
  it('pauses a retained hidden tab and resumes the same mounted scene', () => {
    const { rerender } = render(<Scene />);
    intersection(true);
    expect(screen.getByTestId('scene')).toHaveAttribute('data-animated', 'true');
    rerender(<Scene tabHidden />);
    intersection(false);
    expect(screen.getByTestId('scene')).toHaveAttribute('data-animated', 'false');
    // A visibility notification cannot resume a canvas beneath a hidden tab.
    intersection(true);
    expect(screen.getByTestId('scene')).toHaveAttribute('data-animated', 'false');
    rerender(<Scene />);
    intersection(true);
    expect(screen.getByTestId('scene')).toHaveAttribute('data-animated', 'true');
    expect(observers).toHaveLength(1);
  });

  it('stops viewport animation while the scene is scrolled offscreen', () => {
    render(<Scene />);
    intersection(true);
    intersection(false);
    expect(screen.getByTestId('scene')).toHaveAttribute('data-animated', 'false');
    intersection(true);
    expect(screen.getByTestId('scene')).toHaveAttribute('data-animated', 'true');
  });

  it('honors background documents and reduced motion even when intersecting', () => {
    render(<Scene />);
    intersection(true);
    hidden = true;
    act(() => document.dispatchEvent(new Event('visibilitychange')));
    expect(screen.getByTestId('scene')).toHaveAttribute('data-animated', 'false');
    hidden = false;
    media.matches = true;
    act(() => media.addEventListener.mock.calls[0][1]());
    expect(screen.getByTestId('scene')).toHaveAttribute('data-animated', 'false');
    media.matches = false;
    act(() => media.addEventListener.mock.calls[0][1]());
    expect(screen.getByTestId('scene')).toHaveAttribute('data-animated', 'true');
  });

  it('disconnects observers and listeners after leaving the feature', () => {
    const remove = vi.spyOn(document, 'removeEventListener');
    const { unmount } = render(<Scene />);
    unmount();
    expect(observers[0].disconnect).toHaveBeenCalledOnce();
    expect(media.removeEventListener).toHaveBeenCalledWith('change', expect.any(Function));
    expect(remove).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
  });
});
