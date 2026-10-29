import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor, within } from '../test/render';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildHabit, buildParent } from '../test/factories';
import { buildChallengeGoal } from '../test/challenges';
import { selectDropdown } from '../test/selectDropdown';
import { useAuth } from '../hooks/useApi';
import Habits from './Habits';
import Movement from './Movement';
import Reading from './reading';
import JournalReader from './chronicle/JournalReader';
import Trials from './trials';
import Rewards from './Rewards';
import TreasuryHub from './treasury';
import ChronicleHub from './chronicle';
import Achievements from './Achievements';
import Companions from './bestiary/party/Companions';
import TimelineEntry from './yearbook/TimelineEntry';
import Portfolio from './Portfolio';

// The account remains a real parent. Only its presentation/workspace changes.
vi.mock('../hooks/useSpace', () => ({ useSpace: () => ({
  space: 'personal', isPersonalSpace: true, isFamilySpace: false,
  isParentAccount: true, switchSpace: vi.fn(),
}) }));
vi.mock('framer-motion', async () => ({
  ...await vi.importActual('framer-motion'),
  AnimatePresence: ({ children }) => children,
}));

const PARENT = buildParent({ id: 90, family: { id: 1, timezone: 'America/Phoenix' } });
const RUN = { id: 1, name: 'Run', icon: '🏃', default_intensity: 'medium', skill_tags: [] };

function AccountRole() {
  const { user } = useAuth();
  return <span data-testid="account-role">{user?.role}</span>;
}

function renderPersonal(ui, options) {
  return renderWithProviders(<><AccountRole />{ui}</>, options);
}

beforeEach(() => {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(PARENT)));
});

describe('Parent My space', () => {
  it('creates and taps an own published habit without proposing it to a parent', async () => {
    const tap = spyHandler('post', /\/api\/habits\/9\/log\/$/, { direction: 1, new_strength: 1 });
    const create = spyHandler('post', /\/api\/habits\/$/, { id: 10, user: 90 });
    server.use(tap.handler, create.handler,
      http.get('*/api/habits/', ({ request }) => HttpResponse.json(
        new URL(request.url).searchParams.has('pending') ? [] : [buildHabit({ id: 9, user: 90, name: 'Stretch' })],
      )),
    );
    const { user } = renderPersonal(<Habits />);
    await user.click(await screen.findByRole('button', { name: 'Log progress' }));
    await waitFor(() => expect(tap.calls).toHaveLength(1));
    expect(tap.calls[0]).toMatchObject({ method: 'POST', body: { direction: 1 } });
    expect(tap.calls[0].url).toMatch(/\/api\/habits\/9\/log\/$/);
    await user.click(screen.getByRole('button', { name: 'New habit' }));
    const dialog = screen.getByRole('dialog', { name: 'New habit' });
    expect(within(dialog).queryByLabelText('Child')).toBeNull();
    expect(within(dialog).queryByText(/Your parent will set/)).toBeNull();
    await user.type(within(dialog).getByLabelText('Name'), 'Walk after lunch');
    await user.click(within(dialog).getByRole('button', { name: 'Create habit' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].url).toMatch(/\/api\/habits\/$/);
    expect(create.calls[0].body).toEqual({ name: 'Walk after lunch', icon: '', habit_type: 'positive', max_taps_per_day: 1, user: 90, xp_reward: 5, skill_tags: [] });
    expect(screen.getByTestId('account-role')).toHaveTextContent('parent');
  });

  it('logs personal movement while retaining the parent account role', async () => {
    const log = spyHandler('post', /\/api\/movement-sessions\/$/, { id: 20, user: 90, xp_awarded: 15 });
    server.use(log.handler,
      http.get('*/api/movement-types/', () => HttpResponse.json([RUN])),
      http.get('*/api/movement-sessions/', () => HttpResponse.json([])),
    );
    const { user } = renderPersonal(<Movement />);
    await user.click(await screen.findByRole('button', { name: 'Log' }));
    const dialog = screen.getByRole('dialog', { name: 'Log a session' });
    await waitFor(() => expect(within(dialog).getByLabelText('What did you do?')).toBeEnabled());
    await selectDropdown(user, within(dialog).getByLabelText('What did you do?'), '1');
    await user.click(within(dialog).getByRole('button', { name: 'Log session' }));
    await waitFor(() => expect(log.calls).toHaveLength(1));
    expect(log.calls[0].url).toMatch(/\/api\/movement-sessions\/$/);
    expect(log.calls[0].body).toMatchObject({ movement_type_id: 1, duration_minutes: 30 });
    expect(log.calls[0].body).not.toHaveProperty('user_id');
    expect(screen.getByTestId('account-role')).toHaveTextContent('parent');
  });

  it('saves a book on the parent’s own shelf without a child selector', async () => {
    const create = spyHandler('post', /\/api\/reading-books\/$/, ({ body }) => ({ ...body, id: 12, user: 90 }));
    server.use(create.handler,
      http.get('*/api/reading-books/', () => HttpResponse.json([])),
      http.get('*/api/reading-sessions/', () => HttpResponse.json([])),
      http.get('*/api/reading/summary/', () => HttpResponse.json({ today: '2026-10-27', books_total: 0, total_minutes: 0, total_pages: 0, sessions_total: 0 })),
    );
    const { user } = renderPersonal(<Reading />);
    await user.click((await screen.findAllByRole('button', { name: 'Add a book' }))[0]);
    const dialog = screen.getByRole('dialog', { name: 'Add a book' });
    await user.type(within(dialog).getByLabelText('Book title'), 'A parent’s book');
    await user.click(within(dialog).getByRole('button', { name: 'Save book' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].url).toMatch(/\/api\/reading-books\/$/);
    expect(create.calls[0].body).toEqual({ title: 'A parent’s book', author: '', status: 'reading', interests: [], client_request_id: expect.stringMatching(/^[a-f0-9-]{36}$/) });
    expect(screen.queryByLabelText('Child')).toBeNull();
  });

  it('logs personal reading with truthful private-note labels', async () => {
    let saved = null;
    const create = spyHandler('post', /\/api\/reading-sessions\/$/, ({ body }) => {
      saved = { ...body, id: 13, user: 90, book_title: 'My reading book' };
      return saved;
    });
    server.use(create.handler,
      http.get('*/api/reading-books/', () => HttpResponse.json([{ id: 12, user: 90, title: 'My reading book', author: '', status: 'reading', interests: [] }])),
      http.get('*/api/reading-sessions/', () => HttpResponse.json(saved ? [saved] : [])),
      http.get('*/api/reading/summary/', () => HttpResponse.json({ today: '2026-10-27', books_total: 1, total_minutes: 0, total_pages: 0, sessions_total: 0 })),
    );
    const { user } = renderPersonal(<Reading />);
    await user.click(await screen.findByRole('button', { name: 'Log reading: My reading book' }));
    const dialog = screen.getByRole('dialog', { name: 'Log your reading' });
    expect(within(dialog).getByText('Optional. These notes stay in your personal bookshelf.')).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText('Minutes (optional)'), '10');
    await user.type(within(dialog).getByLabelText('Your reading note (optional)'), 'A thought about the story.');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].url).toMatch(/\/api\/reading-sessions\/$/);
    expect(create.calls[0].body).toMatchObject({ book: 12, duration_minutes: 10, reflection: 'A thought about the story.', client_request_id: expect.any(String) });
    expect(create.calls[0].body).not.toHaveProperty('user_id');
    expect(await screen.findByText('Only me')).toBeInTheDocument();
    expect(screen.queryByText('Shared with parents')).toBeNull();
  });

  it('writes the parent’s personal journal with private sharing by default', async () => {
    const save = spyHandler('post', /\/api\/chronicle\/journal\/$/, ({ body }) => ({ ...body, id: 30, user: 90, kind: 'journal', occurred_on: '2026-10-27' }));
    server.use(save.handler,
      http.get('*/api/chronicle/summary/', () => HttpResponse.json({ chapters: [], current_chapter_year: 2026 })),
      http.get('*/api/chronicle/journal/today/', () => new HttpResponse(null, { status: 204 })),
    );
    const { user } = renderPersonal(<JournalReader />);
    await user.click(await screen.findByRole('button', { name: 'Write today’s entry' }));
    const dialog = screen.getByRole('dialog', { name: 'Write in your journal' });
    expect(within(dialog).getByLabelText('Share with co-parents in my family')).not.toBeChecked();
    await user.type(within(dialog).getByLabelText("What's on your mind?"), 'A peaceful walk after work.');
    await user.click(within(dialog).getByRole('button', { name: 'Save entry' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].url).toMatch(/\/api\/chronicle\/journal\/$/);
    expect(save.calls[0].body).toMatchObject({ summary: 'A peaceful walk after work.', is_private: true, client_entry_id: expect.any(String) });
    expect(save.calls[0].body).not.toHaveProperty('user_id');
  });

  it('lets a parent read their own private timeline entry and its detail', async () => {
    const { user } = renderPersonal(<TimelineEntry entry={{
      id: 31, user: 90, kind: 'journal', title: 'My own memory',
      summary: 'Private adult words.', occurred_on: '2026-10-26', is_private: true,
    }} />);
    await user.click(await screen.findByRole('button', { name: /My own memory/ }));
    const dialog = screen.getByRole('dialog', { name: 'My own memory' });
    expect(within(dialog).getByText('Private adult words.')).toBeInTheDocument();
    expect(within(dialog).getByText('Only me')).toBeInTheDocument();
    expect(within(dialog).queryByText(/only visible to its author/)).toBeNull();
  });

  it('pins a personal challenge and creates a self goal without school or child targeting', async () => {
    const goal = buildChallengeGoal();
    const pin = spyHandler('post', /\/api\/challenges\/goal(?::|%3A)11\/pin\/$/, { pin: goal.id });
    const create = spyHandler('post', /\/api\/challenges\/goals\/$/, { ...goal, id: 'goal:12' });
    server.use(pin.handler, create.handler,
      http.get('*/api/challenges/', () => HttpResponse.json({ results: [goal], pin: null, daily_bonus: null })),
    );
    const { user } = renderPersonal(<Trials />, { route: '/quests?tab=trials' });
    await user.click(await screen.findByRole('button', { name: 'Pin to Today' }));
    await waitFor(() => expect(pin.calls).toHaveLength(1));
    expect(pin.calls[0].url).toMatch(/\/api\/challenges\/goal(?::|%3A)11\/pin\/$/);
    expect(pin.calls[0].body).toEqual({});
    await user.click(screen.getByRole('button', { name: 'Create challenge' }));
    const dialog = screen.getByRole('dialog', { name: 'Create a challenge' });
    expect(within(dialog).queryByLabelText('Child')).toBeNull();
    await user.click(within(dialog).getByRole('button', { name: 'Create challenge' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].url).toMatch(/\/api\/challenges\/goals\/$/);
    expect(create.calls[0].body).toMatchObject({ user_id: 90, trigger_type: 'habit_log', coin_reward: 0, xp_reward: 0, request_id: expect.any(String) });
    expect(screen.queryByRole('button', { name: 'Assign family challenge' })).toBeNull();
  });

  it('spends own Coins through the shop and hides family money controls even on an adjust link', async () => {
    const redeem = spyHandler('post', /\/api\/rewards\/13\/redeem\/$/, { id: 40, status: 'pending', coin_cost_snapshot: 50, reward: { id: 13, name: 'Coffee break' } });
    server.use(redeem.handler,
      http.get('*/api/rewards/', () => HttpResponse.json([{ id: 13, name: 'Coffee break', cost_coins: 50, is_active: true, requires_approval: true }])),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 120 })),
    );
    const { user } = renderPersonal(<Rewards />, { route: '/treasury?tab=bazaar&adjust=1' });
    await user.click(await screen.findByRole('button', { name: /request reward/i }));
    const dialog = screen.getByRole('dialog', { name: /coffee break/i });
    await user.click(within(dialog).getByRole('button', { name: /request reward/i }));
    await waitFor(() => expect(redeem.calls).toHaveLength(1));
    expect(redeem.calls[0].url).toMatch(/\/api\/rewards\/13\/redeem\/$/);
    expect(redeem.calls[0].body).toEqual({});
    expect(screen.queryByRole('button', { name: 'Exchange money for coins' })).toBeNull();
    expect(screen.queryByRole('button', { name: /adjust coins|add reward|edit reward/i })).toBeNull();
    expect(screen.queryByRole('dialog', { name: /adjust coins/i })).toBeNull();
  });

  it('feeds an owned companion using the ordinary server reward workflow', async () => {
    const feed = spyHandler('post', /\/api\/pets\/1\/feed\/$/, { new_growth: 35, growth_added: 5, evolved: false });
    server.use(feed.handler,
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [{ id: 1, species: { name: 'Fox', sprite_key: 'fox', icon: '🦊', slug: 'fox' }, potion: { name: 'Earth', slug: 'earth', rarity: 'common' }, growth_points: 30, is_active: true, evolved_to_mount: false, happiness_level: 'happy' }], mounts: [], total_possible: 15 })),
      http.get('*/api/inventory/', () => HttpResponse.json([{ item: { id: 100, item_type: 'food', name: 'Berries', icon: '🫐' }, quantity: 5 }])),
    );
    const { user } = renderPersonal(<Companions />);
    await user.click(await screen.findByRole('button', { name: 'Feed your companion' }));
    const dialog = await screen.findByRole('dialog', { name: /Care for/ });
    await user.click(within(dialog).getByRole('button', { name: /Berries/ }));
    await waitFor(() => expect(feed.calls).toHaveLength(1));
    expect(feed.calls[0].url).toMatch(/\/api\/pets\/1\/feed\/$/);
    expect(feed.calls[0].body).toEqual({ food_item_id: 100 });
    expect(screen.getByTestId('account-role')).toHaveTextContent('parent');
  });

  it('keeps the personal Rewards hub focused on shop, inventory and savings', async () => {
    renderPersonal(<TreasuryHub />);
    expect(await screen.findByRole('tab', { name: 'Shop' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Inventory' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Savings goals' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Payments' })).toBeNull();
    expect(screen.queryByRole('tab', { name: 'Timecards' })).toBeNull();
  });

  it('keeps school grades out of a parent’s personal Memories', async () => {
    renderPersonal(<ChronicleHub />);
    expect(await screen.findByRole('tab', { name: 'Journal' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Grades' })).toBeNull();
  });

  it('shows personal skills without household catalog management', async () => {
    renderPersonal(<Achievements />);
    expect(await screen.findByText('Track your skill progress')).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Manage' })).toBeNull();
  });

  it('shows personal creations without offering the parent a child bonus submission', async () => {
    server.use(http.get('*/api/portfolio/', () => HttpResponse.json({
      projects: [], homework: [], creations: [{ id: 70, user_id: 90,
        caption: 'My pottery', image: '/synthetic-pottery.png', status: 'logged',
        created_at: '2026-10-27T12:00:00Z', primary_skill_name: 'Pottery' }],
    })));
    renderPersonal(<Portfolio />);
    expect(await screen.findByRole('button', { name: 'View My pottery' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit.*for parent bonus/i })).toBeNull();
  });
});
