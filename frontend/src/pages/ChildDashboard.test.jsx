import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import Dashboard from './Dashboard.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildUser } from '../test/factories.js';
import { buildChallengeGoal, buildDailyBonus } from '../test/challenges';
import { SpriteCatalogContext } from '../providers/spriteCatalog.context';

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}{location.search}</span>;
}

function renderDashboard(extraHandlers = [], catalog = {}) {
  server.use(...extraHandlers);
  return render(
    <MemoryRouter>
      <AuthProvider>
        <SpriteCatalogContext.Provider value={{ getSpriteMeta: (key) => catalog[key] || null }}>
          <Dashboard />
        </SpriteCatalogContext.Provider>
        <LocationProbe />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('ChildDashboard', () => {
  it('lets a child revisit and update today’s note from Today', async () => {
    const user = userEvent.setup();
    let saved = {
      id: 7, date: '2026-10-13', is_today: true,
      affirmation: { text: 'A quiet moment for today.' },
      gratitude_lines: ['Warm bread'], gratitude_paid: true,
      max_lines: 3, max_line_chars: 200, coin_reward: 2,
    };
    const submit = spyHandler('post', /\/api\/wellbeing\/today\/gratitude\/$/, ({ body }) => {
      saved = { ...saved, gratitude_lines: body.lines };
      return { ...saved, freshly_paid: false, coin_awarded: 0 };
    });
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/challenges/daily/', () => HttpResponse.json(null)),
      http.get('*/api/wellbeing/today/', () => HttpResponse.json(saved)),
      submit.handler,
    ]);
    expect(await screen.findByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument();
    const firstLine = await screen.findByRole('textbox', { name: "Today's note" });
    await waitFor(() => expect(firstLine).toHaveValue('Warm bread'));
    expect(screen.getByText("today's note")).toBeInTheDocument();
    expect(screen.getByText('A quiet moment for today.')).toBeInTheDocument();
    await user.clear(firstLine);
    await user.type(firstLine, '  A walk together  ');
    await user.click(screen.getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(submit.calls).toHaveLength(1));
    expect(submit.calls[0].body).toEqual({ lines: ['A walk together'] });
    expect(submit.calls[0].url).toMatch(/\/api\/wellbeing\/today\/gratitude\/$/);
    await waitFor(() => expect(firstLine).toHaveValue('A walk together'));
    expect(screen.queryByText(/first save today earns/i)).toBeNull();
  });

  it('renders active-timer hero when a timer is active', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: { project_title: 'Bird Feeder', elapsed_minutes: 42, project_id: 5 },
          current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0, rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
          next_actions: [],
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getAllByText(/bird feeder/i).length).toBeGreaterThan(0));
  });

  it('renders the since-last-visit summary card from the dashboard payload', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
          next_actions: [],
          since_last_visit: {
            last_seen_at: '2026-06-08T12:00:00Z',
            badges_earned: 3, approvals: 1, coins_earned: 12,
          },
        }),
      ),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/since you were here last/i)).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/3 badges earned · 1 approval · \+12 coins/i),
    ).toBeInTheDocument();
  });

  it('renders the coin sparkline in the Treasury section when coins were earned', async () => {
    const user = userEvent.setup();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 12,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
          next_actions: [],
        }),
      ),
      http.get('*/api/coins/summary-by-day/', () =>
        HttpResponse.json({
          days: 30,
          series: [
            { date: '2026-06-09', earned: 0 },
            { date: '2026-06-10', earned: 12 },
          ],
        }),
      ),
    ]);
    await user.click(await screen.findByRole('button', { name: /rewards & earnings/i }));
    await waitFor(() =>
      expect(
        screen.getByRole('img', { name: /coins earned per day over the last 30 days/i }),
      ).toBeInTheDocument(),
    );
  });

  it('renders pet growth pip and savings goal peek', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [
            { id: 1, title: 'P1', status: 'in_progress', difficulty: 2, milestones_total: 3, milestones_completed: 1 },
          ],
          recent_badges: [{ badge__id: 1, badge__name: 'Gold', badge__icon: '🏅' }],
          savings_goals: [{ id: 1, title: 'Bike', icon: '🚲', current_amount: 20, target_amount: 100, percent_complete: 20 }],
          chores_today: [{ id: 1, title: 'dishes', reward_amount: '1', coin_reward: 5, is_done: false }],
          pending_chore_approvals: 0,
          rpg: {
            level: 3, xp_to_next: 10, xp_percent: 80,
            login_streak: 4, longest_login_streak: 6, perfect_days_count: 1,
            habits_today: [],
          },
          next_actions: [
            { kind: 'chore', id: 1, title: 'dishes', subtitle: 'duty · $1',
              score: 70, due_at: null,
              reward: { money: '1', coins: 5 },
              icon: 'Sparkles', tone: 'moss', action_url: '/chores' },
          ],
        }),
      ),
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({
          pets: [{ id: 1, is_active: true, species: { name: 'Drake', icon: '🐉', sprite_key: 'drake' }, potion: { name: 'Fire', slug: 'fire' }, growth_points: 40 }],
          mounts: [],
        }),
      ),
      http.get('*/api/drops/recent/', () =>
        HttpResponse.json([{ id: 1, item_name: 'Coin', item_icon: '🪙', item_sprite_key: 'coin', item_rarity: 'common', was_salvaged: false }]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/recent items/i)).toBeInTheDocument());
    // Savings peek renders the first goal title even while collapsed.
    expect(screen.getByText(/bike/i)).toBeInTheDocument();
    // Pet growth % visible in the vital pip.
    expect(screen.getByText(/40%/)).toBeInTheDocument();
  });

  it('renders a "no pet" pip when no active pet', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
          next_actions: [],
        }),
      ),
    ]);
    await waitFor(() => expect(screen.getByLabelText(/find a pet/i)).toBeInTheDocument());
  });

  it('uses the recent-drop serializer fields for catalog artwork, rarity, and satchel navigation', async () => {
    const user = userEvent.setup();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () => HttpResponse.json({ next_actions: [] })),
      http.get('*/api/drops/recent/', () => HttpResponse.json([{
        id: 17, item: 24, item_name: 'Sky potion', item_icon: '🧪',
        item_sprite_key: 'sky-potion', item_rarity: 'rare', trigger_type: 'chore_complete',
        quantity: 1, was_salvaged: false, created_at: '2026-10-10T12:00:00Z',
      }])),
    ], { 'sky-potion': { url: '/sprites/sky-potion.png', frames: 1 } });

    const card = await screen.findByRole('button', { name: 'Sky potion — open inventory' });
    expect(screen.getByRole('img', { name: 'Sky potion' })).toHaveAttribute('src', '/sprites/sky-potion.png');
    expect(card).toHaveClass('border-royal/40', 'bg-royal/10');
    expect(screen.getByText('Items earned through your activity')).toBeInTheDocument();
    expect(screen.queryByText(/items found in the last two days/i)).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'Today' })).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    await user.click(card);
    expect(screen.getByTestId('location')).toHaveTextContent('/treasury?tab=satchel');
  });

  it('shows dropped quantities and explains duplicates converted to coins', async () => {
    const user = userEvent.setup();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () => HttpResponse.json({ next_actions: [] })),
      http.get('*/api/drops/recent/', () => HttpResponse.json([
        {
          id: 18, item: 25, item_name: 'Oats', item_icon: '🌾', item_rarity: 'common',
          quantity: 3, was_salvaged: false, created_at: '2026-09-10T12:00:00Z',
        },
        {
          id: 19, item: 26, item_name: 'Moon frame', item_icon: '🌙', item_rarity: 'rare',
          quantity: 1, was_salvaged: true, created_at: '2026-09-09T12:00:00Z',
        },
      ])),
    ]);

    const items = await screen.findByRole('region', { name: 'Recent items' });
    expect(within(items).getByRole('button', { name: 'Oats × 3 — open inventory' })).toHaveTextContent('Oats × 3');
    expect(within(items).getByRole('button', { name: 'Moon frame (converted to coins) — open inventory' })).toHaveTextContent('Converted to coins');
    await user.click(within(items).getByRole('button', { name: /view inventory/i }));
    expect(screen.getByTestId('location')).toHaveTextContent('/treasury?tab=satchel');
  });

  it('opens earned badges when a recent accolade is selected', async () => {
    const user = userEvent.setup();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () => HttpResponse.json({
        next_actions: [], recent_badges: [{ badge__id: 9, badge__name: 'Kind helper', badge__icon: '🏅' }],
      })),
    ]);
    await user.click(await screen.findByRole('button', { name: /recent badges/i }));
    await user.click(await screen.findByRole('button', { name: 'Kind helper — view earned badges' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/atlas?tab=badges');
  });

  it('renders the top recommendation and preserves task kinds in the ranked list', async () => {
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          role: 'child',
          active_timer: null,
          chores_today: [], // deprecated — still on wire
          homework: { dashboard: { overdue: [], today: [], upcoming: [] } },
          rpg: {
            level: 0, login_streak: 0, longest_login_streak: 0,
            perfect_days_count: 0, last_active_date: null, habits_today: [],
          },
          next_actions: [
            { kind: 'homework', id: 42, title: 'Math workbook',
              subtitle: 'Math · due tomorrow', score: 60, due_at: '2026-04-17',
              reward: null, icon: 'BookOpen', tone: 'royal', action_url: '/homework' },
            { kind: 'chore', id: 7, title: 'Clean Room',
              subtitle: 'duty · $1.00', score: 34, due_at: null,
              reward: { money: '1.00', coins: 2 },
              icon: 'Sparkles', tone: 'moss', action_url: '/chores' },
          ],
        }),
      ),
    ]);

    await screen.findAllByText('Math workbook');
    // Hero shows top item — and the quest log echoes it; both should be present.
    expect(screen.getAllByText('Math workbook').length).toBeGreaterThanOrEqual(1);
    // Hero exposes a "Submit Math workbook" button (homework kind label).
    expect(screen.getByRole('button', { name: /submit math workbook/i })).toBeInTheDocument();
    const tasks = screen.getByRole('region', { name: 'Your tasks' });
    expect(within(tasks).getByText('Homework')).toBeInTheDocument();
    expect(within(tasks).getByText('Chore')).toBeInTheDocument();
    expect(screen.getByText('Clean Room')).toBeInTheDocument();
  });

  it('clicking an open homework row opens the submit sheet', async () => {
    const user = userEvent.setup();
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', () =>
        HttpResponse.json({
          active_timer: null, current_balance: 0, coin_balance: 0,
          this_week: { hours_worked: 0, earnings: 0 },
          active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
          pending_chore_approvals: 0,
          rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
          next_actions: [
            { kind: 'homework', id: 99, title: 'Poem recital',
              subtitle: 'Reading · due tomorrow', score: 60, due_at: null,
              reward: null, icon: 'BookOpen', tone: 'royal', action_url: '/homework' },
          ],
        }),
      ),
    ]);
    // Hero exposes a "Submit Poem recital" button; the quest log exposes
    // the per-row "Complete Poem recital" check-glyph. Either should open
    // the same sheet.
    const row = await screen.findByRole('button', { name: /complete poem recital/i });
    await user.click(row);
    // Sheet content renders on document.body via portal.
    await waitFor(() =>
      expect(document.body.textContent).toMatch(/affix photographic evidence/i),
    );
    expect(document.body.textContent).toMatch(/poem recital/i);
  });

  it('tapping a habit on the today log posts to /habits/{id}/log/ and refetches', async () => {
    const user = userEvent.setup();
    const tap = spyHandler('post', /\/api\/habits\/\d+\/log\/$/, { ok: true });
    const dashboard = vi.fn(() =>
      HttpResponse.json({
        active_timer: null, current_balance: 0, coin_balance: 0,
        this_week: { hours_worked: 0, earnings: 0 },
        active_projects: [], recent_badges: [], savings_goals: [], chores_today: [],
        pending_chore_approvals: 0,
        rpg: {
          level: 1, xp_to_next: 10, xp_percent: 0,
          login_streak: 0, longest_login_streak: 0, perfect_days_count: 0,
          habits_today: [{ id: 7, name: 'Read 30min', icon: '📖', strength: 7, taps_today: 2, max_taps_per_day: 5 }],
        },
        next_actions: [
          { kind: 'habit', id: 7, title: 'Read 30min',
            subtitle: 'keep your 1-day streak', score: 65, due_at: null,
            reward: null, icon: 'Flame', tone: 'ember', action_url: '/habits' },
        ],
      }),
    );
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', dashboard),
      tap.handler,
    ]);

    // Quest log exposes per-row "Complete Read 30min" check-glyph.
    const buttons = await screen.findAllByRole('button', { name: /complete read 30min/i });
    await user.click(buttons[0]);

    await waitFor(() => expect(tap.calls).toHaveLength(1));
    expect(tap.calls[0].body).toEqual({ direction: 1 });
    expect(tap.calls[0].url).toMatch(/\/habits\/7\/log\/$/);
    await waitFor(() => expect(dashboard.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it('completing a chore from the today log posts to /chores/{id}/complete/ and refetches', async () => {
    const user = userEvent.setup();
    const complete = spyHandler('post', /\/api\/chores\/\d+\/complete\/$/, { ok: true });
    const dashboard = vi.fn(() =>
      HttpResponse.json({
        active_timer: null, current_balance: 0, coin_balance: 0,
        this_week: { hours_worked: 0, earnings: 0 },
        active_projects: [], recent_badges: [], savings_goals: [],
        chores_today: [{ id: 4, title: 'dishes', reward_amount: '1', coin_reward: 5, is_done: false }],
        pending_chore_approvals: 0,
        rpg: { login_streak: 0, longest_login_streak: 0, perfect_days_count: 0 },
        next_actions: [
          { kind: 'chore', id: 4, title: 'dishes', subtitle: 'duty · $1',
            score: 70, due_at: null,
            reward: { money: '1', coins: 5 },
            icon: 'Sparkles', tone: 'moss', action_url: '/chores' },
        ],
      }),
    );
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/dashboard/', dashboard),
      complete.handler,
    ]);

    // The quest log exposes the checkbox control with aria-label "Complete {title}".
    const buttons = await screen.findAllByRole('button', { name: /complete dishes/i });
    await user.click(buttons[0]);

    await waitFor(() => expect(complete.calls).toHaveLength(1));
    expect(complete.calls[0].body).toEqual({ notes: '' });
    expect(complete.calls[0].url).toMatch(/\/chores\/4\/complete\/$/);
    await waitFor(() => expect(dashboard.mock.calls.length).toBeGreaterThanOrEqual(2));
  });
});


describe('Today challenge availability', () => {
  it('shows a retry when challenges cannot load instead of claiming nothing is pinned', async () => {
    const user = userEvent.setup();
    let requests = 0;
    renderDashboard([
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/challenges/', () => {
        requests += 1;
        return requests === 1 ? HttpResponse.json({ error: 'Challenges are temporarily unavailable.' }, { status: 503 }) : HttpResponse.json({ results: [], pin: null, daily_bonus: null });
      }),
    ]);
    expect(await screen.findByRole('alert')).toHaveTextContent('Challenges are temporarily unavailable.');
    expect(screen.queryByRole('button', { name: 'Choose a challenge to pin' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry challenges' }));
    expect(await screen.findByRole('button', { name: 'Choose a challenge to pin' })).toBeInTheDocument();
    expect(requests).toBe(2);
  });
});

describe('Today action hierarchy', () => {
  const action = (kind, id, title, score) => ({
    kind, id, title, score, subtitle: kind === 'chore' ? 'Daily chore' : 'Due later this week',
    due_at: null, reward: null, icon: kind === 'homework' ? 'BookOpen' : 'Sparkles',
    tone: kind === 'homework' ? 'royal' : 'moss', action_url: '/quests',
  });
  const seed = (overrides = {}) => [
    http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    http.get('*/api/challenges/daily/', () => HttpResponse.json(null)),
    http.get('*/api/dashboard/', () => HttpResponse.json({
      active_timer: null, coin_balance: 125, current_balance: 0,
      this_week: { hours_worked: 0, earnings: 0 },
      active_projects: [], recent_badges: [], savings_goals: [],
      next_actions: [], rpg: { login_streak: 0, level: 3 }, ...overrides,
    })),
  ];

  it('keeps the urgent chore visible before later homework even with a running timer', async () => {
    const user = userEvent.setup();
    renderDashboard(seed({
      active_timer: { project_title: 'Birdhouse', project_id: 5, elapsed_minutes: 12 },
      next_actions: [action('chore', 7, 'Feed the animals', 70), ...Array.from({ length: 5 }, (_, i) => action('homework', i + 20, `Later homework ${i + 1}`, 30))],
    }));
    await screen.findByRole('heading', { name: 'Birdhouse' });
    expect(screen.getByRole('button', { name: 'Complete Feed the animals' })).toBeInTheDocument();
    expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('Feed the animals');
    expect(screen.queryByRole('button', { name: 'Complete Later homework 5' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /show all 6 tasks/i }));
    const rows = screen.getAllByRole('listitem');
    expect(rows).toHaveLength(6);
    expect(rows[0]).toHaveTextContent('Feed the animals');
    expect(rows[5]).toHaveTextContent('Later homework 5');
    await user.click(screen.getByRole('button', { name: 'Show fewer' }));
    expect(screen.getAllByRole('listitem')).toHaveLength(5);
    expect(screen.getAllByRole('listitem')[0]).toHaveTextContent('Feed the animals');
  });

  it('puts the next action before status and exposes project continuation before reflection and earnings', async () => {
    const user = userEvent.setup();
    renderDashboard(seed({
      next_actions: [action('chore', 7, 'Feed the animals', 70)],
      active_projects: [{ id: 42, title: 'Build a birdhouse', status: 'in_progress', milestones_completed: 1, milestones_total: 4 }],
      since_last_visit: { badges_earned: 1, approvals: 2, coins_earned: 5 },
    }));
    const hero = await screen.findByRole('heading', { name: 'Feed the animals' });
    const coins = screen.getByRole('button', { name: '125 coins' });
    expect(hero.compareDocumentPosition(coins) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const project = screen.getByRole('button', { name: /Build a birdhouse/i });
    const reflection = await screen.findByRole('heading', { name: 'For you, today' });
    expect(project.compareDocumentPosition(reflection) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const earnings = screen.getByRole('button', { name: /Rewards & earnings/i });
    expect(earnings).toHaveAttribute('aria-expanded', 'false');
    expect(project.compareDocumentPosition(earnings) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await user.click(project);
    expect(screen.getByTestId('location')).toHaveTextContent('/quests/ventures/42');
  });

  it('uses an honest no-work state without claiming a parent has never added work', async () => {
    renderDashboard(seed({
      chores_today: [{ id: 7, title: 'Submitted chore', status: 'pending' }],
      rpg: { habits_today: [{ id: 9, name: 'Read a book' }] },
    }));
    await screen.findByRole('heading', { name: 'Today', level: 1 });
    expect(screen.queryByText(/once your parent adds/i)).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'No urgent tasks right now' })).toBeInTheDocument();
    expect(screen.getByText(/submitted work may still be waiting for review/i)).toBeInTheDocument();
  });

  it('keeps the exact pinned goal after work and shows automatic bonus receipts inside rewards', async () => {
    const user = userEvent.setup();
    const pinned = buildChallengeGoal({ pinned: true });
    renderDashboard([
      ...seed({
        next_actions: [action('chore', 7, 'Feed the animals', 70)],
        active_projects: [{ id: 42, title: 'Build a birdhouse', status: 'in_progress', milestones_completed: 1, milestones_total: 4 }],
      }),
      http.get('*/api/challenges/', () => HttpResponse.json({
        results: [buildChallengeGoal({ id: 'goal:12', name: 'An unpinned goal' }), pinned],
        pin: pinned.id,
        daily_bonus: buildDailyBonus({ completed: true, awarded: true, coins_awarded: 7, xp_awarded: 9, receipt_id: 'daily:11' }),
      })),
    ]);
    const goal = await screen.findByRole('heading', { name: pinned.name });
    const project = screen.getByRole('region', { name: 'Continue a project' });
    const tasks = screen.getByRole('region', { name: 'Your tasks' });
    expect(tasks.compareDocumentPosition(project) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(project.compareDocumentPosition(goal) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText('An unpinned goal')).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: "Today's bonus" })).not.toBeInTheDocument();
    const earnings = screen.getByRole('button', { name: /Rewards & earnings/i });
    expect(earnings).toHaveTextContent('Daily bonus earned');
    await user.click(earnings);
    expect(await screen.findByText('Bonus earned · +7 coins · +9 XP')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /claim/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'View challenge' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/quests?tab=trials&goal=goal%3A11');
  });
});
