import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders, userEvent } from '../../test/render.jsx';
import { server } from '../../test/server.js';
import { buildParent } from '../../test/factories.js';
import GuideSection from './GuideSection.jsx';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return {
    ...a,
    AnimatePresence: ({ children }) => children,
    motion: {
      ...a.motion,
      li: ({ children }) => <li>{children}</li>,
      div: ({ children, initial: _initial, animate: _animate, exit: _exit, transition: _transition, ...props }) => <div {...props}>{children}</div>,
    },
  };
});

const entries = [
  {
    slug: 'study',
    title: 'Study',
    icon: '📚',
    audience_title: "The scholar's desk",
    chapter: 'daily_life',
    summary: 'Homework is school duty: XP and progress, not coins.',
    kid_voice: 'Study pages are for learning.',
    mechanics: [
      'Homework pays no money and no Coins.',
      'Approved submissions award XP through homework skill tags.',
    ],
    parent_knobs: {
      settings: [{ key: 'HOMEWORK_LATE_CUTOFF_DAYS', label: 'Late cutoff', value: 3 }],
      powers_badges: ['homework_planned_ahead'],
      content_sources: ['Assignments author fixed XP skill tags.'],
    },
    economy: {
      money: false,
      coins: false,
      xp: true,
      drops: true,
      quest_progress: true,
      streak_credit: true,
    },
    unlocked: true,
    trained: true,
    trial_template: 'tap_and_reward',
    trial: { prompt: 'tap to feel it', payoff: '+5 XP' },
  },
  {
    slug: 'streaks',
    title: 'Streaks',
    icon: '🔥',
    chapter: 'rpg_layer',
    summary: 'Daily return without harsh punishment.',
    kid_voice: 'A streak is the little flame that says you came back.',
    mechanics: ['Missing a day never destroys earned Coins, XP, items, badges, pets, or memories.'],
    parent_knobs: { settings: [], powers_badges: ['streak_days'], content_sources: [] },
    economy: {
      money: false,
      coins: true,
      xp: false,
      drops: true,
      quest_progress: false,
      streak_credit: true,
    },
    unlocked: true,
    trained: true,
    trial_template: 'tap_and_reward',
    trial: { prompt: 'tap to feel it', payoff: '+5 XP' },
  },
];

function mockLorebook() {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
    http.get('*/api/lorebook/', () =>
      HttpResponse.json({ entries, counts: { unlocked: 2, trained: 2, total: 2 } }),
    ),
  );
}

describe('GuideSection', () => {
  it('renders the parent economy diagram from lorebook data', async () => {
    mockLorebook();
    renderWithProviders(<GuideSection />, { withAuth: 'parent' });

    await screen.findByRole('heading', { name: /economy diagram/i });
    expect(screen.getByText(/why doesn't homework pay coins/i)).toBeInTheDocument();

    const studyRow = screen.getByRole('row', { name: /study/i });
    const cells = withinRow(studyRow);
    expect(cells).toContain('—');
    expect(cells).toContain('✓');
  });

  it('opens an entry with parent knobs expanded by default', async () => {
    mockLorebook();
    const user = userEvent.setup();
    renderWithProviders(<GuideSection />, { withAuth: 'parent' });

    await user.click(await screen.findByRole('button', { name: /study · inked/i }));

    await screen.findByRole('dialog', { name: /study/i });
    expect(screen.getByText(/homework pays no money and no coins/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/HOMEWORK_LATE_CUTOFF_DAYS/i)).toBeVisible(),
    );
  });
});

function withinRow(row) {
  return Array.from(row.querySelectorAll('td span')).map((node) => node.textContent);
}
