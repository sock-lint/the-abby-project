import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import SigilCodex from './SigilCodex';
import { COLLECTIONS } from './collections.constants';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

describe('SigilCodex', () => {
  it('renders the empty-state when no badges have been forged', () => {
    renderWithProviders(<SigilCodex allBadges={[]} earnedBadges={[]} onSelect={() => {}} />);
    expect(screen.getByText(/no badges have been forged yet/i)).toBeInTheDocument();
  });

  it('renders all seven collection chapters plus the incipit band', () => {
    const allBadges = [
      { id: 1, name: 'First Project', rarity: 'common', icon: '🥇', criterion_type: 'first_project' },
      { id: 2, name: 'Centennial', rarity: 'legendary', icon: '💯', criterion_type: 'badges_earned_count', criterion_value: 100 },
    ];
    renderWithProviders(
      <SigilCodex allBadges={allBadges} earnedBadges={[]} onSelect={() => {}} />,
    );

    // Heading "Sigil Case" from the incipit band
    expect(screen.getByRole('heading', { name: 'Sigil Case' })).toBeInTheDocument();

    // Every chapter has its own <section aria-labelledby>
    for (const c of COLLECTIONS) {
      expect(screen.getByRole('region', { name: c.name })).toBeInTheDocument();
    }

    // Incipit count "0 of 2 sealed"
    expect(screen.getByText(/0 of 2/)).toBeInTheDocument();
  });

  it('forwards onSelect with the sigil payload when a badge is clicked', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    const allBadges = [
      {
        id: 7,
        name: 'Night Owl',
        rarity: 'rare',
        icon: '🦉',
        criterion_type: 'late_night',
      },
    ];
    renderWithProviders(
      <SigilCodex
        allBadges={allBadges}
        earnedBadges={[{ badge: allBadges[0], earned_at: '2026-04-10' }]}
        onSelect={spy}
      />,
    );

    await user.click(screen.getByRole('button', { name: /Night Owl/ }));
    expect(spy).toHaveBeenCalledWith({
      badge: allBadges[0],
      earned: true,
      earnedAt: '2026-04-10',
    });
  });
});
