import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor, within } from '@testing-library/react';
import { renderWithProviders, userEvent } from '../../test/render.jsx';
import { server } from '../../test/server.js';
import { buildParent } from '../../test/factories.js';
import { spyHandler } from '../../test/spy.js';
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
    slug: 'movement',
    title: 'Movement',
    icon: '🏃',
    chapter: 'daily_life',
    summary: 'Log physical activity and follow progress toward movement goals.',
    kid_voice: 'Record how you moved today.',
    mechanics: ['Save the activity, duration, intensity, and optional distance.'],
    parent_knobs: { settings: [], powers_badges: [], content_sources: [] },
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
    trial_template: 'observe',
    trial: { prompt: 'Review a saved session.', payoff: 'Movement recorded' },
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

function mockLorebook(responseEntries = entries) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
    http.get('*/api/lorebook/', () =>
      HttpResponse.json({ entries: responseEntries }),
    ),
  );
}

describe('GuideSection', () => {
  it('keeps the rewards comparison closed until requested and renders the activity columns', async () => {
    mockLorebook();
    const user = userEvent.setup();
    renderWithProviders(<GuideSection />, { withAuth: 'parent' });

    const comparison = await screen.findByText('Compare rewards by activity');
    const table = screen.getByRole('table', { hidden: true });
    expect(table).not.toBeVisible();
    expect(screen.getByRole('button', { name: 'Study · read guide' })).toBeVisible();
    await user.click(comparison);

    expect(screen.getByRole('table')).toBeVisible();
    expect(screen.getByText(/see which activities earn money/i)).toBeInTheDocument();
    for (const label of ['Entry', 'Money', 'Coins', 'XP', 'Drops', 'Challenge', 'Streak']) {
      expect(screen.getByRole('columnheader', { name: label })).toBeVisible();
    }

    const studyRow = screen.getByRole('row', { name: /study/i });
    const cells = within(studyRow).getAllByRole('cell');
    expect(within(cells[0]).getByLabelText('no')).toBeInTheDocument();
    expect(within(cells[1]).getByLabelText('no')).toBeInTheDocument();
    expect(within(cells[2]).getByLabelText('yes')).toBeInTheDocument();
    const movementCells = within(screen.getByRole('row', { name: /movement/i })).getAllByRole('cell');
    expect(movementCells.map((cell) => within(cell).getByLabelText(/yes|no/).getAttribute('aria-label')))
      .toEqual(['no', 'no', 'yes', 'yes', 'yes', 'yes']);
    await user.click(comparison);
    expect(table).not.toBeVisible();
  });

  it('opens the parent reference directly regardless of child discovery and training flags', async () => {
    mockLorebook(entries.map((entry) => ({ ...entry, unlocked: false, trained: false })));
    const training = spyHandler('patch', /\/api\/auth\/me\/$/, {});
    server.use(training.handler);
    const user = userEvent.setup();
    renderWithProviders(<GuideSection />, {
      withAuth: 'parent',
      route: '/manage?tab=Guide&trial=study',
    });

    const topic = await screen.findByRole('button', { name: 'Study · read guide' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByText(/completed|discovered|practice/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Daily Life, 2 topics' })).toBeInTheDocument();
    await user.click(topic);

    await screen.findByRole('dialog', { name: /study/i });
    expect(screen.getByText(/homework pays no money and no coins/i)).toBeInTheDocument();
    expect(screen.getByText(/reference defaults/i)).toBeVisible();
    expect(screen.getByText(/these values are documentation, not your family's current settings/i)).toBeVisible();
    await waitFor(() =>
      expect(screen.getByText(/HOMEWORK_LATE_CUTOFF_DAYS/i)).toBeVisible(),
    );
    expect(screen.queryByText(/current default|configurable settings/i)).not.toBeInTheDocument();
    await user.click(screen.getByText('Close', { selector: 'button' }));
    await user.click(screen.getByRole('button', { name: 'Movement · read guide' }));
    const movement = await screen.findByRole('dialog', { name: 'Movement' });
    expect(within(movement).getByText('Save the activity, duration, intensity, and optional distance.')).toBeVisible();
    expect(training.calls).toHaveLength(0);
  });

  it('shows a failed reference read and retries without claiming there are no topics', async () => {
    mockLorebook();
    let reads = 0;
    server.use(http.get('*/api/lorebook/', () => {
      reads += 1;
      return reads === 1
        ? HttpResponse.json({ detail: 'Guide unavailable' }, { status: 503 })
        : HttpResponse.json({ entries });
    }));
    const user = userEvent.setup();
    renderWithProviders(<GuideSection />, { withAuth: 'parent' });

    expect(await screen.findByRole('alert')).toBeVisible();
    expect(screen.queryByText('No guide topics available yet.')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('button', { name: 'Study · read guide' })).toBeVisible();
    expect(reads).toBe(2);
  });
});
