import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

const ROUTE_TITLES = {
  '/': 'Today',
  '/quests': 'Quests',
  '/bestiary': 'Bestiary',
  '/treasury': 'Treasury',
  '/atlas': 'Atlas',
  '/chronicle': 'Chronicle',
  '/sigil': 'Character',
  '/clock': 'Clock',
  '/manage': 'Manage',
  '/activity': 'Activity',
  '/settings': 'Settings',
};

export default function RouteAnnouncer() {
  const { pathname } = useLocation();
  const ref = useRef(null);

  useEffect(() => {
    const title = ROUTE_TITLES[pathname]
      || pathname.replace(/^\//, '').split('/')[0].replace(/-/g, ' ')
      || 'Page';
    const label = `Navigated to ${title}`;
    if (ref.current) ref.current.textContent = label;
    document.title = `${title} — Hyrule Field Notes`;
  }, [pathname]);

  return (
    <div
      ref={ref}
      role="status"
      aria-live="assertive"
      aria-atomic="true"
      className="sr-only"
    />
  );
}
