import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

const ROUTE_TITLES = {
  '/': 'Today',
  '/quests': 'Tasks',
  '/bestiary': 'Pets',
  '/treasury': 'Rewards',
  '/atlas': 'Progress',
  '/chronicle': 'Memories',
  '/sigil': 'Profile',
  '/profile/customize': 'Customize avatar',
  '/clock': 'Time tracking',
  '/manage': 'Manage',
  '/manage/usage': 'Usage',
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
    document.title = `${title} — The Abby Project`;
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
