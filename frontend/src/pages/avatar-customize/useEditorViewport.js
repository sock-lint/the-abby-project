import { useLayoutEffect, useState } from 'react';

export default function useEditorViewport(ref) {
  const [height, setHeight] = useState(null);
  useLayoutEffect(() => {
    const header = document.querySelector('[data-journal-sticky-header="true"]');
    const navigation = document.querySelector('[data-journal-bottom-nav="true"]');
    const measure = () => {
      if (!ref.current) return;
      const viewport = window.visualViewport;
      const bottom = (viewport?.height || window.innerHeight) + (viewport?.offsetTop || 0);
      const nav = navigation?.getBoundingClientRect();
      const navInset = nav?.height > 0 && nav.top < bottom ? Math.max(0, bottom - nav.top) : 0;
      const top = Math.max(ref.current.getBoundingClientRect().top, header?.getBoundingClientRect().bottom || 0);
      setHeight(Math.max(120, Math.floor(bottom - top - navInset - 12)));
    };
    const observer = new ResizeObserver(measure);
    [ref.current?.parentElement, header, navigation].filter(Boolean).forEach((element) => observer.observe(element));
    window.addEventListener('resize', measure);
    window.visualViewport?.addEventListener('resize', measure);
    measure();
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', measure);
      window.visualViewport?.removeEventListener('resize', measure);
    };
  }, [ref]);
  return height;
}
