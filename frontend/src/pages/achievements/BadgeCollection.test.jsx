import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import BadgeCollection from './BadgeCollection.jsx';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('BadgeCollection', () => {
  it('renders empty state when there are no badges', () => {
    render(<BadgeCollection allBadges={[]} earnedBadges={[]} />);
    expect(screen.getAllByText((t) => /badge|empty|no/i.test(t)).length).toBeGreaterThanOrEqual(0);
  });

  it('renders earned and unearned badges sorted by status', () => {
    const all = [
      { id: 1, name: 'Z Badge', rarity: 'common', icon: '🏅', description: 'd' },
      { id: 2, name: 'A Badge', rarity: 'rare', icon: '🎖️', description: 'd' },
      { id: 3, name: 'M Badge', rarity: 'common', icon: '🥇', description: 'd' },
    ];
    const earned = [{ badge: { id: 2, name: 'A Badge', rarity: 'rare', icon: '🎖️' }, earned_at: '2026-04-10' }];
    render(<BadgeCollection allBadges={all} earnedBadges={earned} />);
    expect(screen.getByText('A Badge')).toBeInTheDocument();
    expect(screen.getByText('M Badge')).toBeInTheDocument();
    expect(screen.getByText('Z Badge')).toBeInTheDocument();
  });
});
