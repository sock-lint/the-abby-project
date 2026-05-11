import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import SigilCodex from './SigilCodex';
import { COLLECTIONS } from './collections.constants';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

beforeEach(() => {
  // jsdom doesn't implement scrollIntoView; stub so TomeShelf's effect
  // doesn't throw when activeId changes.
  Element.prototype.scrollIntoView = vi.fn();
  try { window.localStorage.clear(); } catch { /* ignore */ }
});

describe('SigilCodex', () => {
  it('renders the empty-state when no badges have been forged', () => {
    renderWithProviders(<SigilCodex allBadges={[]} earnedBadges={[]} onSelect={() => {}} />);
    expect(screen.getByText(/no badges have been forged yet/i)).toBeInTheDocument();
  });

  it('renders an incipit + a shelf with one spine per chapter', () => {
    const allBadges = [
      { id: 1, name: 'First Project', rarity: 'common', icon: '🥇', criterion_type: 'first_project' },
      { id: 2, name: 'Centennial', rarity: 'legendary', icon: '💯', criterion_type: 'badges_earned_count', criterion_value: 100 },
    ];
    renderWithProviders(
      <SigilCodex allBadges={allBadges} earnedBadges={[]} onSelect={() => {}} />,
    );

    // Heading "Sigil Case" from the incipit band
    expect(screen.getByRole('heading', { name: 'Sigil Case' })).toBeInTheDocument();

    // Shelf is a tablist with one tab per chapter
    const shelf = screen.getByRole('tablist', { name: /sigil reliquary chapters/i });
    expect(shelf).toBeInTheDocument();
    for (const c of COLLECTIONS) {
      expect(screen.getByRole('tab', { name: new RegExp(c.name, 'i') })).toBeInTheDocument();
    }

    // Incipit count "0 of 2 sealed"
    expect(screen.getByText(/0 of 2/)).toBeInTheDocument();
  });

  it('opens only the active chapter\'s folio at any time', async () => {
    const user = userEvent.setup();
    const allBadges = [
      // Ventures-only: 'first_project' lives in §II Ventures.
      { id: 1, name: 'First Project', rarity: 'common', icon: '🥇', criterion_type: 'first_project' },
    ];
    renderWithProviders(
      <SigilCodex allBadges={allBadges} earnedBadges={[]} onSelect={() => {}} />,
    );

    // No earned sigils → default lands on Chronos (first chapter overall).
    expect(screen.getByRole('region', { name: 'Chronos' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Ventures' })).toBeNull();

    // Switching the spine swaps which folio renders.
    await user.click(screen.getByRole('tab', { name: /Ventures/i }));
    expect(screen.getByRole('region', { name: 'Ventures' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Chronos' })).toBeNull();
  });

  it('defaults to the first chapter that has any earned sigil', () => {
    const allBadges = [
      { id: 1, name: 'First Project', rarity: 'common', icon: '🥇', criterion_type: 'first_project' },
      { id: 7, name: 'Night Owl', rarity: 'rare', icon: '🦉', criterion_type: 'late_night' },
    ];
    renderWithProviders(
      <SigilCodex
        allBadges={allBadges}
        earnedBadges={[{ badge: allBadges[0], earned_at: '2026-04-10' }]}
        onSelect={() => {}}
      />,
    );
    // 'first_project' is in §II Ventures, so the codex should land on
    // Ventures (the first chapter with any earned sigil), not Chronos.
    expect(screen.getByRole('region', { name: 'Ventures' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Chronos' })).toBeNull();
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

    // 'late_night' is in §I Chronos and the user has it earned, so the
    // codex lands on Chronos and the sigil is visible.
    await user.click(screen.getByRole('button', { name: /Night Owl/ }));
    expect(spy).toHaveBeenCalledWith({
      badge: allBadges[0],
      earned: true,
      earnedAt: '2026-04-10',
    });
  });

  it('persists the active chapter to localStorage', async () => {
    const user = userEvent.setup();
    const allBadges = [
      { id: 1, name: 'First Project', rarity: 'common', icon: '🥇', criterion_type: 'first_project' },
    ];
    renderWithProviders(
      <SigilCodex allBadges={allBadges} earnedBadges={[]} onSelect={() => {}} />,
    );
    await user.click(screen.getByRole('tab', { name: /Adventure/i }));
    expect(window.localStorage.getItem('atlas:sigil-codex:active-chapter')).toBe('adventure');
  });
});
