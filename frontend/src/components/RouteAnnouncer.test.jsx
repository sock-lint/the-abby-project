import { afterEach, describe, expect, it } from 'vitest';
import { Link } from 'react-router-dom';
import { renderWithProviders, screen } from '../test/render';
import RouteAnnouncer from './RouteAnnouncer';

const originalTitle = document.title;
afterEach(() => { document.title = originalTitle; });

describe('RouteAnnouncer', () => {
  it('uses the current app brand while announcing the Today route', () => {
    renderWithProviders(<RouteAnnouncer />, { withAuth: false });
    expect(document.title).toBe('Today — The Abby Project');
    const announcement = screen.getByRole('status');
    expect(announcement).toHaveTextContent('Navigated to Today');
    expect(announcement).toHaveAttribute('aria-live', 'assertive');
    expect(announcement).toHaveAttribute('aria-atomic', 'true');
  });

  it('updates the branded title and live announcement after navigation', async () => {
    const { user } = renderWithProviders(
      <><RouteAnnouncer /><Link to="/quests">View tasks</Link></>,
      { withAuth: false },
    );
    await user.click(screen.getByRole('link', { name: 'View tasks' }));
    expect(document.title).toBe('Tasks — The Abby Project');
    expect(screen.getByRole('status')).toHaveTextContent('Navigated to Tasks');
  });

  it('names the staff usage route', () => {
    renderWithProviders(<RouteAnnouncer />, { withAuth: false, route: '/manage/usage' });
    expect(document.title).toBe('Usage — The Abby Project');
  });
});
