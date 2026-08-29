import { useEffect, useState } from 'react';

// The on-screen keyboard *overlays* a `position: fixed; bottom: 0` sheet
// rather than shrinking it: `dvh` tracks the layout viewport, which the
// keyboard doesn't resize on iOS, nor on Android Chrome without an
// `interactive-widget=resizes-content` viewport hint. The focused input gets
// scrolled into the visible strip, but the field's error text and the action
// row below it stay behind the keyboard.
//
// `visualViewport` does see the keyboard, so we measure how many pixels of the
// window it is covering and hand the number back for the sheet to sit above.
//
// Returns 0 when there is no keyboard — and on any browser without
// `visualViewport` — so callers can treat a falsy value as "nothing to
// compensate for" and keep their static layout.

// Below this, the delta is address-bar / toolbar chrome rather than a keyboard.
const MIN_INSET_PX = 80;

export default function useVisualViewportInset() {
  const [inset, setInset] = useState(0);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return undefined;

    const measure = () => {
      // offsetTop is non-zero while the page is pinch-zoomed/panned; including
      // it keeps the math honest instead of reporting a phantom keyboard.
      const covered = window.innerHeight - vv.height - vv.offsetTop;
      setInset(covered > MIN_INSET_PX ? Math.round(covered) : 0);
    };

    measure();
    vv.addEventListener('resize', measure);
    vv.addEventListener('scroll', measure);
    return () => {
      vv.removeEventListener('resize', measure);
      vv.removeEventListener('scroll', measure);
    };
  }, []);

  return inset;
}
