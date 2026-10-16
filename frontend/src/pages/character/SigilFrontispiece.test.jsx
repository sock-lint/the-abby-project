import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import SigilFrontispiece from './SigilFrontispiece';

describe('SigilFrontispiece', () => {
  it('recognizes a server-confirmed terminal level without an empty next-level promise', () => {
    renderWithProviders(<SigilFrontispiece
      profile={{ display_name: 'Abby', level: 6, total_xp: 2500, xp_in_level: 0, xp_needed_for_level: 0 }}
      onOpenTrophyPicker={() => {}}
    />);
    expect(screen.getByText('Highest level')).toBeInTheDocument();
    expect(screen.queryByText(/toward the next level/)).toBeNull();
  });

  it('shows the profile picture inside the equipped frame', () => {
    renderWithProviders(<SigilFrontispiece
      profile={{ display_name: 'Abby', active_frame: { metadata: { border_color: '#866329' } } }}
      profilePicture="/media/avatars/abby.png"
      onOpenTrophyPicker={() => {}}
    />);
    const picture = screen.getByRole('img', { name: 'Your profile picture' });
    expect(picture).toHaveAttribute('src', '/media/avatars/abby.png');
    expect(picture.parentElement).toHaveStyle({ boxShadow: '0 0 0 3px var(--color-ink-page-aged), 0 0 0 4px #866329, 0 0 0 6px var(--color-ink-page-shadow)' });
  });

  it('keeps the initial as the fallback when no picture is saved', () => {
    renderWithProviders(<SigilFrontispiece profile={{ display_name: 'Abby' }} onOpenTrophyPicker={() => {}} />);
    expect(screen.queryByRole('img', { name: 'Your profile picture' })).toBeNull();
    expect(screen.getAllByText('A').length).toBeGreaterThan(0);
  });

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
    expect(screen.getByRole('heading', { level: 1, name: 'Abby' })).toBeInTheDocument();
    expect(screen.getByText('Your profile')).toBeInTheDocument();
  });

  it('summarizes the three confirmed activity stats', () => {
    renderWithProviders(
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
    expect(screen.getByText('Streak')).toBeInTheDocument();
    expect(screen.getByText('7 days')).toBeInTheDocument();
    expect(screen.getByText('Perfect days')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('Best streak')).toBeInTheDocument();
    expect(screen.getByText('12 days')).toBeInTheDocument();
  });

  it('does not invent a next-level percentage from the level', () => {
    renderWithProviders(
      <SigilFrontispiece profile={{ display_name: 'Abby', level: 5 }} onOpenTrophyPicker={() => {}} />,
    );
    expect(screen.queryByText(/toward the next level/)).toBeNull();
  });

  it('shows an explicitly supplied zero XP progress accurately', () => {
    renderWithProviders(
      <SigilFrontispiece profile={{ display_name: 'Abby', level: 5, xp_in_level: 0, xp_needed_for_level: 100 }} onOpenTrophyPicker={() => {}} />,
    );
    expect(screen.getByText('0% toward the next level')).toBeInTheDocument();
  });

  it('renders an empty trophy slot when active_trophy_badge is null', () => {
    renderWithProviders(
      <SigilFrontispiece
        profile={{ display_name: 'Abby', level: 1, active_trophy_badge: null }}
        onOpenTrophyPicker={() => {}}
      />,
    );
    const slot = screen.getByRole('button', { name: /no trophy badge/i });
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
    expect(screen.getByRole('button', { name: /Trophy badge: Night Owl/i })).toBeInTheDocument();
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
    await user.click(screen.getByRole('button', { name: /no trophy badge/i }));
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
