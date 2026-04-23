import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import BadgeDetailSheet from './BadgeDetailSheet';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const earnedEntry = {
  badge: {
    id: 1,
    name: 'Perfect Joinery',
    description: 'Cut 10 mortise & tenon joints.',
    icon: '🏆',
    rarity: 'rare',
    xp_bonus: 50,
    criterion_type: 'milestones_completed',
    criterion_value: 10,
  },
  earned: true,
  earnedAt: '2026-04-10T14:22:00Z',
};

const unearnedEntry = {
  badge: {
    ...earnedEntry.badge,
    id: 2,
    name: 'Centennial',
    rarity: 'legendary',
    criterion_type: 'badges_earned_count',
    criterion_value: 100,
  },
  earned: false,
  earnedAt: null,
};

describe('BadgeDetailSheet', () => {
  it('renders inside a dialog labeled by the badge name', () => {
    renderWithProviders(<BadgeDetailSheet entry={earnedEntry} onClose={() => {}} />);
    expect(screen.getByRole('dialog', { name: 'Perfect Joinery' })).toBeInTheDocument();
  });

  it('shows rarity ribbon and description', () => {
    renderWithProviders(<BadgeDetailSheet entry={earnedEntry} onClose={() => {}} />);
    expect(screen.getByText(/rare/i)).toBeInTheDocument();
    expect(screen.getByText(/mortise & tenon/i)).toBeInTheDocument();
  });

  it('shows the earned date when earned', () => {
    renderWithProviders(<BadgeDetailSheet entry={earnedEntry} onClose={() => {}} />);
    expect(screen.getByText(/^sealed\s+/i)).toBeInTheDocument();
  });

  it('shows a "not yet earned" line when unearned', () => {
    renderWithProviders(<BadgeDetailSheet entry={unearnedEntry} onClose={() => {}} />);
    expect(screen.getByText(/not yet earned/i)).toBeInTheDocument();
  });

  it('shows the xp bonus when present and > 0', () => {
    renderWithProviders(<BadgeDetailSheet entry={earnedEntry} onClose={() => {}} />);
    expect(screen.getByText(/\+50\s*XP/i)).toBeInTheDocument();
  });

  it('shows a collection chip naming the reliquary chapter', () => {
    renderWithProviders(<BadgeDetailSheet entry={earnedEntry} onClose={() => {}} />);
    const chip = screen.getByText(/from the reliquary of Ventures/);
    expect(chip).toBeInTheDocument();
    expect(chip.textContent).toMatch(/§II/);
  });

  it('shows a "to earn" unlock hint line for unearned badges', () => {
    renderWithProviders(<BadgeDetailSheet entry={unearnedEntry} onClose={() => {}} />);
    expect(screen.getByText(/to earn/i)).toBeInTheDocument();
    expect(screen.getByText(/Earn 100 badges/)).toBeInTheDocument();
  });

  it('shows a "you earned this by" retrospective line for earned badges', () => {
    renderWithProviders(<BadgeDetailSheet entry={earnedEntry} onClose={() => {}} />);
    expect(screen.getByText(/you earned this by/i)).toBeInTheDocument();
    expect(screen.getByText(/Complete 10 milestones/)).toBeInTheDocument();
  });

  it('renders a ladder strip when two+ badges share a criterion_type', () => {
    const ladderAll = [
      { id: 10, name: 'Novice', rarity: 'common', criterion_type: 'projects_completed', criterion_value: 1 },
      { id: 11, name: 'Adept', rarity: 'uncommon', criterion_type: 'projects_completed', criterion_value: 10 },
      { id: 12, name: 'Master', rarity: 'rare', criterion_type: 'projects_completed', criterion_value: 50 },
    ];
    const entry = { badge: ladderAll[1], earned: false, earnedAt: null };
    renderWithProviders(
      <BadgeDetailSheet
        entry={entry}
        onClose={() => {}}
        allBadges={ladderAll}
        earnedIds={new Set([10])}
      />,
    );
    // BottomSheet portals into document.body, so query there.
    const ladder = document.body.querySelector('[data-ladder="true"]');
    expect(ladder).not.toBeNull();
    const rungs = ladder.querySelectorAll('[data-ladder-rung]');
    expect(rungs.length).toBe(3);
    expect(rungs[0].getAttribute('data-ladder-rung')).toBe('earned');
    expect(rungs[1].getAttribute('data-ladder-rung')).toBe('current');
    expect(rungs[2].getAttribute('data-ladder-rung')).toBe('locked');
  });

  it('omits the ladder strip when the badge has no siblings', () => {
    renderWithProviders(
      <BadgeDetailSheet entry={earnedEntry} onClose={() => {}} allBadges={[earnedEntry.badge]} />,
    );
    expect(document.body.querySelector('[data-ladder="true"]')).toBeNull();
  });
});
