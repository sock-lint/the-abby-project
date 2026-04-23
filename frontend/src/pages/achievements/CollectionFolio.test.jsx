import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, userEvent } from '../../test/render';
import CollectionFolio from './CollectionFolio';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const chronos = {
  id: 'chronos',
  rubric: '§I',
  letter: 'C',
  name: 'Chronos',
  kicker: 'the cadence of hours',
  criteria: ['hours_worked'],
};

function defaultCounts() {
  return {
    common: { earned: 0, total: 0 },
    uncommon: { earned: 0, total: 0 },
    rare: { earned: 0, total: 0 },
    epic: { earned: 0, total: 0 },
    legendary: { earned: 0, total: 0 },
  };
}

describe('CollectionFolio', () => {
  it('renders rubric + letter + name in a labelled section', () => {
    renderWithProviders(
      <CollectionFolio
        collection={chronos}
        badges={[]}
        earned={0}
        total={0}
        rarityCounts={defaultCounts()}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByRole('region', { name: 'Chronos' })).toBeInTheDocument();
    expect(screen.getByText('§I')).toBeInTheDocument();
    expect(screen.getByText(/the cadence of hours/)).toBeInTheDocument();
  });

  it('shows the "no seals yet" whisper when the chapter is empty', () => {
    renderWithProviders(
      <CollectionFolio
        collection={chronos}
        badges={[]}
        earned={0}
        total={0}
        rarityCounts={defaultCounts()}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText(/no seals yet in this chapter/i)).toBeInTheDocument();
  });

  it('renders each badge and forwards onSelect when a sigil is clicked', async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    const badges = [
      {
        earned: false,
        earnedAt: null,
        badge: { id: 1, name: 'Early Bird', rarity: 'common', icon: '🌅', criterion_type: 'early_bird' },
      },
      {
        earned: true,
        earnedAt: '2026-04-15T10:00:00Z',
        badge: { id: 2, name: 'Night Owl', rarity: 'rare', icon: '🦉', criterion_type: 'late_night' },
      },
    ];
    renderWithProviders(
      <CollectionFolio
        collection={chronos}
        badges={badges}
        earned={1}
        total={2}
        rarityCounts={{ ...defaultCounts(), common: { earned: 0, total: 1 }, rare: { earned: 1, total: 1 } }}
        onSelect={spy}
      />,
    );
    expect(screen.getByText('Early Bird')).toBeInTheDocument();
    expect(screen.getByText('Night Owl')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Night Owl/ }));
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ earned: true, earnedAt: '2026-04-15T10:00:00Z' }),
    );
  });

  it('shows the sealed count in the header', () => {
    renderWithProviders(
      <CollectionFolio
        collection={chronos}
        badges={[]}
        earned={2}
        total={5}
        rarityCounts={defaultCounts()}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText(/2 of 5/)).toBeInTheDocument();
  });
});
