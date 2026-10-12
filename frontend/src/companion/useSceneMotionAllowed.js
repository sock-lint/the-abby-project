import { useEffect, useState } from 'react';

/** Pause scene animation when its retained tab or viewport is not visible. */
export default function useSceneMotionAllowed(sceneRef) {
  const [allowed, setAllowed] = useState(false);

  useEffect(() => {
    const element = sceneRef.current;
    if (!element) return undefined;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    let intersects = false;
    const update = () => setAllowed(
      intersects && !element.closest('[hidden]') && !document.hidden && !media.matches,
    );
    let observer;
    if (typeof IntersectionObserver === 'function') {
      observer = new IntersectionObserver((entries) => {
        const entry = entries.find((item) => item.target === element);
        if (!entry) return;
        intersects = entry.isIntersecting;
        update();
      });
      observer.observe(element);
    } else {
      // Older browsers can still pause retained hidden tabs and background
      // documents. Current target platforms use the viewport observer above.
      intersects = element.getClientRects().length > 0;
      update();
    }
    document.addEventListener('visibilitychange', update);
    media.addEventListener('change', update);
    return () => {
      observer?.disconnect();
      document.removeEventListener('visibilitychange', update);
      media.removeEventListener('change', update);
    };
  }, [sceneRef]);

  return allowed;
}
