import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import BadgeSigilGrid from './BadgeSigilGrid';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

describe('BadgeSigilGrid', () => {
  it('renders empty state when there are no badges', () => {
    renderWithProviders(<BadgeSigilGrid allBadges={[]} earnedBadges={[]} onSelect={() => {}} />);
    expect(screen.getByText(/no badges/i)).toBeInTheDocument();
  });

  it('renders all badges with earned/unearned sorting preserved', () => {
    const all = [
      { id: 1, name: 'Z Badge', rarity: 'common', icon: '🏅', description: 'd' },
      { id: 2, name: 'A Badge', rarity: 'rare', icon: '🎖️', description: 'd' },
      { id: 3, name: 'M Badge', rarity: 'common', icon: '🥇', description: 'd' },
    ];
    const earned = [
      { badge: { id: 2, name: 'A Badge', rarity: 'rare', icon: '🎖️' }, earned_at: '2026-04-10' },
    ];
    renderWithProviders(
      <BadgeSigilGrid allBadges={all} earnedBadges={earned} onSelect={() => {}} />,
    );
    expect(screen.getByText('A Badge')).toBeInTheDocument();
    expect(screen.getByText('M Badge')).toBeInTheDocument();
    expect(screen.getByText('Z Badge')).toBeInTheDocument();

    // Earned first — sigil order in DOM puts A Badge before the unearned ones.
    const names = screen.getAllByText(/Badge$/).map((n) => n.textContent);
    expect(names[0]).toBe('A Badge');
  });

  it('renders earned vs unearned sigils with distinct data attributes', () => {
    const all = [
      { id: 1, name: 'Alpha', rarity: 'common', icon: '🏅', description: '' },
      { id: 2, name: 'Beta', rarity: 'rare', icon: '🎖️', description: '' },
    ];
    const earned = [
      { badge: { id: 2, name: 'Beta', rarity: 'rare', icon: '🎖️' }, earned_at: '2026-04-10' },
    ];
    const { container } = renderWithProviders(
      <BadgeSigilGrid allBadges={all} earnedBadges={earned} onSelect={() => {}} />,
    );
    const sigils = container.querySelectorAll('[data-sigil="true"]');
    expect(sigils.length).toBe(2);
    const states = Array.from(sigils).map((s) => s.getAttribute('data-earned'));
    expect(states).toContain('true');
    expect(states).toContain('false');
  });
});
