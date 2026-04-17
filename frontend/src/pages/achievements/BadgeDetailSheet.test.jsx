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
  },
  earned: true,
  earnedAt: '2026-04-10T14:22:00Z',
};

const unearnedEntry = {
  badge: { ...earnedEntry.badge, id: 2, name: 'Centennial', rarity: 'legendary' },
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
});
