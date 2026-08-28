import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import SwipeableImage from './SwipeableImage.jsx';

// framer-motion's pointer pipeline doesn't run under jsdom, so capture the
// drag handler off the rendered element and drive it directly.
let capturedDragEnd = null;
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  const MOTION_ONLY = [
    'drag', 'dragConstraints', 'dragElastic', 'dragMomentum', 'onDragEnd',
  ];
  return {
    ...actual,
    motion: new Proxy({}, {
      get: (_t, tag) => function MotionStub(props) {
        capturedDragEnd = props.onDragEnd;
        const domProps = { ...props };
        MOTION_ONLY.forEach((k) => delete domProps[k]);
        const Tag = tag;
        return <Tag {...domProps} />;
      },
    }),
  };
});

function renderImage(overrides = {}) {
  const handlers = {
    onPrev: vi.fn(), onNext: vi.fn(), onClose: vi.fn(), ...overrides,
  };
  render(
    <SwipeableImage src="/photo.jpg" alt="A birdhouse" {...handlers} />,
  );
  return handlers;
}

const fling = (x, y = 0) => capturedDragEnd({}, { offset: { x, y } });

describe('SwipeableImage', () => {
  it('renders the image', () => {
    renderImage();
    expect(screen.getByAltText('A birdhouse')).toBeInTheDocument();
  });

  it('flinging left advances, flinging right goes back', () => {
    const h = renderImage();
    fling(-120);
    expect(h.onNext).toHaveBeenCalledTimes(1);
    fling(120);
    expect(h.onPrev).toHaveBeenCalledTimes(1);
    expect(h.onClose).not.toHaveBeenCalled();
  });

  it('flinging down closes the viewer', () => {
    const h = renderImage();
    fling(0, 160);
    expect(h.onClose).toHaveBeenCalledTimes(1);
    expect(h.onNext).not.toHaveBeenCalled();
  });

  it('ignores short drags', () => {
    const h = renderImage();
    fling(-30, 20);
    expect(h.onNext).not.toHaveBeenCalled();
    expect(h.onPrev).not.toHaveBeenCalled();
    expect(h.onClose).not.toHaveBeenCalled();
  });

  it('a mostly-sideways drag advances instead of closing', () => {
    const h = renderImage();
    fling(-140, 120);
    expect(h.onNext).toHaveBeenCalledTimes(1);
    expect(h.onClose).not.toHaveBeenCalled();
  });

  it('does not advance past the ends when the handler is absent', () => {
    const h = renderImage({ onNext: undefined });
    expect(() => fling(-120)).not.toThrow();
    expect(h.onPrev).not.toHaveBeenCalled();
  });
});
