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
      <><RouteAnnouncer /><Link to="/quests">Explore quests</Link></>,
      { withAuth: false },
    );
    await user.click(screen.getByRole('link', { name: 'Explore quests' }));
    expect(document.title).toBe('Quests — The Abby Project');
    expect(screen.getByRole('status')).toHaveTextContent('Navigated to Quests');
  });
});
