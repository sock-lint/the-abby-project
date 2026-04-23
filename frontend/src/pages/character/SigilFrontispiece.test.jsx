import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import SigilFrontispiece from './SigilFrontispiece';

describe('SigilFrontispiece', () => {
  it('renders the display name as the h1', () => {
    renderWithProviders(
      <SigilFrontispiece
        profile={{
          display_name: 'Abby',
          username: 'abby',
          level: 3,
          login_streak: 7,
          longest_login_streak: 12,
          perfect_days_count: 4,
          active_trophy_badge: null,
        }}
        onOpenTrophyPicker={() => {}}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Abby' })).toBeInTheDocument();
  });

  it('renders all three vital pips', () => {
    const { container } = renderWithProviders(
      <SigilFrontispiece
        profile={{
          display_name: 'Abby',
          level: 3,
          login_streak: 7,
          longest_login_streak: 12,
          perfect_days_count: 4,
        }}
        onOpenTrophyPicker={() => {}}
      />,
    );
    expect(container.querySelector('[data-streak-glyph="streak"]')).not.toBeNull();
    expect(container.querySelector('[data-streak-glyph="perfect"]')).not.toBeNull();
    expect(container.querySelector('[data-streak-glyph="best"]')).not.toBeNull();
  });

  it('renders an empty trophy slot when active_trophy_badge is null', () => {
    renderWithProviders(
      <SigilFrontispiece
        profile={{ display_name: 'Abby', level: 1, active_trophy_badge: null }}
        onOpenTrophyPicker={() => {}}
      />,
    );
    const slot = screen.getByRole('button', { name: /no hero seal/i });
    expect(slot).toBeInTheDocument();
  });

  it('renders the trophy slot filled when a trophy is set', () => {
    renderWithProviders(
      <SigilFrontispiece
        profile={{
          display_name: 'Abby',
          level: 5,
          active_trophy_badge: {
            id: 7,
            name: 'Night Owl',
            rarity: 'rare',
            icon: '\ud83e\udd89',
          },
        }}
        onOpenTrophyPicker={() => {}}
      />,
    );
    expect(screen.getByRole('button', { name: /Hero seal: Night Owl/i })).toBeInTheDocument();
  });

  it('clicking the trophy slot opens the picker', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(
      <SigilFrontispiece
        profile={{ display_name: 'Abby', level: 1, active_trophy_badge: null }}
        onOpenTrophyPicker={spy}
      />,
    );
    await user.click(screen.getByRole('button', { name: /no hero seal/i }));
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('renders the active title chip when one is set', () => {
    renderWithProviders(
      <SigilFrontispiece
        profile={{
          display_name: 'Abby',
          level: 2,
          active_title: { id: 1, name: 'Adept', metadata: { text: 'Adept of Flame' } },
        }}
        onOpenTrophyPicker={() => {}}
      />,
    );
    expect(screen.getByText('Adept of Flame')).toBeInTheDocument();
  });
});
