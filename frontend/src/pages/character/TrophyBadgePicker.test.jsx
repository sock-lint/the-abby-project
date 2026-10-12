import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, userEvent } from '../../test/render';
import TrophyBadgePicker from './TrophyBadgePicker';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const allBadges = [
  { id: 1, name: 'First Project', rarity: 'common', icon: '\ud83e\udd47', criterion_type: 'first_project' },
  { id: 2, name: 'Apprentice', rarity: 'common', icon: '\ud83d\udd28', criterion_type: 'projects_completed', criterion_value: 5 },
  { id: 3, name: 'Night Owl', rarity: 'rare', icon: '\ud83e\udd89', criterion_type: 'late_night' },
  { id: 4, name: 'Scholar', rarity: 'uncommon', icon: '\ud83d\udcda', criterion_type: 'skill_level_reached', criterion_value: 5 },
];

const earnedBadges = [
  { badge: allBadges[0], earned_at: '2026-04-10' },
  { badge: allBadges[2], earned_at: '2026-04-15' },
];

describe('TrophyBadgePicker', () => {
  it('keeps an earned badge selectable even when it is absent from the available catalog', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const stored = { id: 90, name: 'Earlier collector badge', rarity: 'rare', icon: '🏅', criterion_type: 'pet_species_owned', catalog_available: false };
    const { getByRole } = renderWithProviders(<TrophyBadgePicker allBadges={[]} earnedBadges={[{ badge: stored, earned_at: '2026-04-10' }]} onSelect={onSelect} onClose={() => {}} />);
    await user.click(getByRole('button', { name: /Earlier collector badge/ }));
    expect(onSelect).toHaveBeenCalledWith(90);
  });
  it('renders inside a dialog labelled by the sheet title', () => {
    const { getByRole } = renderWithProviders(
      <TrophyBadgePicker
        allBadges={allBadges}
        earnedBadges={earnedBadges}
        currentTrophyId={null}
        onSelect={() => {}}
        onClose={() => {}}
      />,
    );
    expect(getByRole('dialog', { name: /choose your trophy badge/i })).toBeInTheDocument();
  });

  it('only renders earned badges, grouped by collection', () => {
    renderWithProviders(
      <TrophyBadgePicker
        allBadges={allBadges}
        earnedBadges={earnedBadges}
        currentTrophyId={null}
        onSelect={() => {}}
        onClose={() => {}}
      />,
    );
    // Earned sigils: First Project (Ventures), Night Owl (Chronos).
    const byName = (n) => document.body.querySelector(`button[aria-label^="${n}"]`);
    expect(byName('First Project')).not.toBeNull();
    expect(byName('Night Owl')).not.toBeNull();
    expect(document.body.querySelector('#trophy-chapter-chronos').parentElement
      .querySelector('[data-chapter-marker="1"]')).toHaveTextContent('1');
    expect(document.body.querySelector('#trophy-chapter-ventures').parentElement
      .querySelector('[data-chapter-marker="2"]')).toHaveTextContent('2');
    // Unearned: Apprentice, Scholar shouldn't appear in the picker.
    expect(byName('Apprentice')).toBeNull();
    expect(byName('Scholar')).toBeNull();
  });

  it('shows an empty state when the user has no earned badges', () => {
    const { getByText } = renderWithProviders(
      <TrophyBadgePicker
        allBadges={allBadges}
        earnedBadges={[]}
        currentTrophyId={null}
        onSelect={() => {}}
        onClose={() => {}}
      />,
    );
    expect(getByText(/haven.{0,3}t earned any badges yet/i)).toBeInTheDocument();
  });

  it('clicking a sigil fires onSelect with its id', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(
      <TrophyBadgePicker
        allBadges={allBadges}
        earnedBadges={earnedBadges}
        currentTrophyId={null}
        onSelect={spy}
        onClose={() => {}}
      />,
    );
    const target = document.body.querySelector('button[aria-label^="First Project"]');
    await user.click(target);
    expect(spy).toHaveBeenCalledWith(1);
  });

  it('clicking the current trophy clears it (null payload)', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    renderWithProviders(
      <TrophyBadgePicker
        allBadges={allBadges}
        earnedBadges={earnedBadges}
        currentTrophyId={3}
        onSelect={spy}
        onClose={() => {}}
      />,
    );
    // A "current" chip should have rendered above the selected sigil.
    expect(document.body.querySelector('[data-trophy-current-marker="true"]'))
      .not.toBeNull();
    const target = document.body.querySelector('button[aria-label^="Night Owl"]');
    await user.click(target);
    expect(spy).toHaveBeenCalledWith(null);
  });
});
