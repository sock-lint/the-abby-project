import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { useAuth } from '../../hooks/useApi';
import { renderWithProviders, screen, waitFor, within, act } from '../../test/render';
import { server } from '../../test/server';
import { buildUser, buildParent } from '../../test/factories';
import { selectDropdown } from '../../test/selectDropdown';
import { spyHandler } from '../../test/spy';
import { PulseContext } from '../../providers/pulseContext';
import Reading from './index';

const BOOK = { id: 12, user: 7, title: 'The Wild Robot', author: 'Peter Brown', status: 'reading', interests: ['animals', 'science'] };
const SECOND = { ...BOOK, id: 13, title: 'A Different Story', author: 'Another Author' };
const SESSION = { id: 42, user: 7, book: 12, book_title: BOOK.title, book_author: BOOK.author, occurred_on: '2026-10-15', duration_minutes: 20, pages_read: 14, section: 'Chapter 2', reflection: 'Roz learned to listen.', format: 'print', reaction: 'liked' };
const SUMMARY = { books_total: 2, books_finished: 1, sessions_total: 4, total_minutes: 85, total_pages: 60, today: '2026-10-16', timezone: 'America/Phoenix' };
const ADVENTURE = { day: SUMMARY.today, target_minutes: 10, minutes_credited: 4, remaining_minutes: 6, earned: false, base_xp: 15, base_coins: 5, xp_awarded: 0, coins_awarded: 0, skill_name: 'Reading Comprehension' };
const REWARD = { day: SUMMARY.today, xp_awarded: 30, coins_awarded: 10 };
const SUGGESTION = { id: 'wild-robot', title: 'The Wild Robot', author: 'Peter Brown', interests: ['animals', 'science'], age_min: 8, age_max: 12, description: 'A robot makes a home in the wild.', source_url: 'https://www.hachettebookgroup.com/titles/peter-brown/the-wild-robot/9780316381994/', reason: 'For your interest in science.' };
function stub({ books = [BOOK, SECOND], sessions = [], parent = false } = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(parent ? buildParent({ id: 90, family: { id: 1 } }) : buildUser({ id: 7 }))),
    http.get('*/api/children/', () => HttpResponse.json([{ id: 7, username: 'abby' }, { id: 8, username: 'ben' }])),
    http.get('*/api/reading-books/', () => HttpResponse.json({ count: books.length, next: null, results: books })),
    http.get('*/api/reading-sessions/', () => HttpResponse.json({ count: sessions.length, next: null, results: sessions })),
    http.get('*/api/reading/summary/', () => HttpResponse.json(SUMMARY)),
  );
}
async function addBook(user) {
  await user.click((await screen.findAllByRole('button', { name: 'Add a book' }))[0]);
  return screen.findByRole('dialog', { name: 'Add a book' });
}

describe('Reading bookshelf', () => {
  it('shows honest empty states, server totals and all shelf filters', async () => {
    stub({ books: [], sessions: [] });
    renderWithProviders(<Reading />);
    expect(await screen.findByText('Your next story starts here.')).toBeInTheDocument();
    expect(screen.getByText(/Nothing logged yet/)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Reading/ })).toHaveAttribute('aria-selected', 'true');
    for (const name of ['Want to read', 'Finished', 'Paused']) expect(screen.getByRole('tab', { name: new RegExp(name) })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Log reading' })).toBeDisabled();
    expect(screen.getAllByText('85').length).toBeGreaterThan(0);
    expect(screen.queryByText(/\bXP\b|\bcoins\b/i)).toBeNull();
  });

  it('POSTs a title, author, shelf and selected interests with an idempotency key', async () => {
    stub({ books: [] });
    const post = spyHandler('post', /\/api\/reading-books\/$/, ({ body }) => ({ ...body, id: 33, user: 7 }));
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />);
    const dialog = await addBook(user);
    await user.type(within(dialog).getByLabelText('Book title'), 'Charlotte’s Web');
    await user.type(within(dialog).getByLabelText('Author (optional)'), 'E. B. White');
    await selectDropdown(user, within(dialog).getByLabelText('Shelf'), 'want_to_read');
    await user.click(within(dialog).getByLabelText('Friendship'));
    await user.click(within(dialog).getByRole('button', { name: 'Save book' }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    expect(post.calls[0].body).toEqual({ title: 'Charlotte’s Web', author: 'E. B. White', status: 'want_to_read', interests: ['friendship'], client_request_id: expect.stringMatching(/^[a-f0-9-]{36}$/) });
    expect(await screen.findByText(/saved to Want to read/)).toBeInTheDocument();
  });

  it('keeps input and maps validation errors to the title field', async () => {
    stub();
    const post = spyHandler('post', /\/api\/reading-books\/$/, HttpResponse.json({ title: ['Please use a book title.'] }, { status: 400 }));
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />);
    const dialog = await addBook(user);
    await user.type(within(dialog).getByLabelText('Book title'), 'My story');
    await user.click(within(dialog).getByRole('button', { name: 'Save book' }));
    expect(await screen.findByText('Please use a book title.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Book title')).toHaveValue('My story');
    expect(within(dialog).getByLabelText('Book title')).toHaveAttribute('aria-invalid', 'true');
    expect(within(dialog).getByRole('button', { name: 'Save book' })).toBeEnabled();
  });

  it('PATCHes book edits without changing ownership or the creation key', async () => {
    stub();
    const patch = spyHandler('patch', /\/api\/reading-books\/12\/$/, ({ body }) => ({ ...BOOK, ...body }));
    server.use(patch.handler);
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('button', { name: `Edit book: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit book' });
    await selectDropdown(user, within(dialog).getByLabelText('Shelf'), 'finished');
    await user.click(within(dialog).getByRole('button', { name: 'Save book' }));
    await waitFor(() => expect(patch.calls).toHaveLength(1));
    expect(patch.calls[0].body).toEqual({ title: BOOK.title, author: BOOK.author, status: 'finished', interests: BOOK.interests });
    expect(await screen.findByText(/saved to Finished/)).toBeInTheDocument();
  });

  it('preserves books with history after the DELETE endpoint refuses removal', async () => {
    stub();
    const deletion = spyHandler('delete', /\/api\/reading-books\/12\/$/, HttpResponse.json({ detail: 'Book has sessions.' }, { status: 409 }));
    server.use(deletion.handler);
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('button', { name: `Remove book: ${BOOK.title}` }));
    const confirm = await screen.findByRole('alertdialog', { name: 'Remove book?' });
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));
    expect(await screen.findByText(/This book has reading history/)).toBeInTheDocument();
    expect(deletion.calls).toHaveLength(1);
    expect(screen.getByRole('article', { name: BOOK.title })).toBeInTheDocument();
  });
});

describe('Reading sessions', () => {
  it.each([
    ['want_to_read', 'Want to read'], ['paused', 'Paused'],
  ])('shows a newly logged %s book on Reading only after the server confirms its shelf', async (status, label) => {
    stub({ books: [{ ...BOOK, status }] });
    let saved = false;
    let release;
    let shelfReads = 0;
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, ({ body }) => {
      saved = true;
      return { ...SESSION, ...body };
    });
    server.use(post.handler, http.get('*/api/reading-books/', async () => {
      shelfReads += 1;
      if (!saved) return HttpResponse.json([{ ...BOOK, status }]);
      await new Promise((resolve) => { release = resolve; });
      return HttpResponse.json([BOOK]);
    }));
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('tab', { name: new RegExp(label) }));
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    await user.type(within(dialog).getByLabelText('Pages read (optional)'), '2');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    expect(await screen.findByText(/Reading saved for/)).toBeInTheDocument();
    expect(post.calls).toHaveLength(1);
    expect(post.calls[0].body).toMatchObject({ book: BOOK.id, pages_read: 2, client_request_id: expect.any(String) });
    expect(screen.getByRole('tab', { name: new RegExp(label) })).toHaveAttribute('aria-selected', 'true');
    await waitFor(() => expect(release).toBeDefined());
    await act(async () => { release(); });
    await waitFor(() => expect(screen.getByRole('tab', { name: /^Reading/ })).toHaveAttribute('aria-selected', 'true'));
    expect(screen.getByRole('article', { name: BOOK.title })).toBeInTheDocument();
    expect(shelfReads).toBe(2);
  });

  it.each([
    { status: 'finished', label: 'Finished', editing: false, action: 'logging a finished book' },
    { status: 'paused', label: 'Paused', editing: true, action: 'editing an existing log' },
  ])('keeps the current shelf after $action', async ({ status, label, editing }) => {
    stub({ books: [{ ...BOOK, status }], sessions: editing ? [SESSION] : [] });
    const write = editing
      ? spyHandler('patch', /\/api\/reading-sessions\/42\/$/, ({ body }) => ({ ...SESSION, ...body }))
      : spyHandler('post', /\/api\/reading-sessions\/$/, ({ body }) => ({ ...SESSION, ...body }));
    let saved = false;
    server.use(write.handler, http.get('*/api/reading-books/', () => {
      saved = write.calls.length > 0;
      // An edit must not navigate even if another client changed the shelf.
      return HttpResponse.json([{ ...BOOK, author: saved ? 'Updated shelf author' : BOOK.author, status: editing && saved ? 'reading' : status }]);
    }));
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('tab', { name: new RegExp(label) }));
    await user.click(await screen.findByRole('button', { name: `${editing ? 'Edit log' : 'Log reading'}: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: editing ? 'Edit reading log' : 'Log your reading' });
    if (!editing) await user.type(within(dialog).getByLabelText('Pages read (optional)'), '2');
    await user.click(within(dialog).getByRole('button', { name: editing ? 'Save changes' : 'Save reading' }));
    expect(await screen.findByText(editing ? /Reading changes saved for/ : /Reading saved for/)).toBeInTheDocument();
    if (editing) await waitFor(() => expect(screen.getByRole('tab', { name: /^Reading/ })).toHaveTextContent('1'));
    else expect(await screen.findByText('Updated shelf author')).toBeInTheDocument();
    expect(write.calls).toHaveLength(1);
    expect(screen.getByRole('tab', { name: new RegExp(label) })).toHaveAttribute('aria-selected', 'true');
  });

  it('keeps Want to read and the form open when a new log is rejected', async () => {
    stub({ books: [{ ...BOOK, status: 'want_to_read' }] });
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, HttpResponse.json({ pages_read: ['Please correct the page count.'] }, { status: 400 }));
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('tab', { name: /Want to read/ }));
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    await user.type(within(dialog).getByLabelText('Pages read (optional)'), '2');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    expect(await within(dialog).findByText('Please correct the page count.')).toBeInTheDocument();
    expect(post.calls).toHaveLength(1);
    expect(screen.getByRole('tab', { name: /Want to read/ })).toHaveAttribute('aria-selected', 'true');
    expect(within(dialog).getByLabelText('Pages read (optional)')).toHaveValue(2);
  });

  it('keeps the saved receipt and current shelf when its refresh fails', async () => {
    stub({ books: [{ ...BOOK, status: 'paused' }] });
    let saved = false;
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, ({ body }) => {
      saved = true;
      return { ...SESSION, ...body };
    });
    server.use(post.handler, http.get('*/api/reading-books/', () => saved
      ? HttpResponse.json({ detail: 'Bookshelf refresh unavailable.' }, { status: 503 })
      : HttpResponse.json([{ ...BOOK, status: 'paused' }])));
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('tab', { name: /Paused/ }));
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    await user.type(within(dialog).getByLabelText('Pages read (optional)'), '2');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    expect(await screen.findByText('Bookshelf refresh unavailable.')).toBeInTheDocument();
    expect(screen.getByText(/Reading saved for/)).toBeInTheDocument();
    expect(post.calls).toHaveLength(1);
    expect(screen.getByRole('tab', { name: /Paused/ })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('article', { name: BOOK.title })).toBeInTheDocument();
  });

  it('preserves a shelf choice made while the saved log refresh is pending', async () => {
    stub({ books: [{ ...BOOK, status: 'want_to_read' }] });
    let saved = false;
    let release;
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, ({ body }) => {
      saved = true;
      return { ...SESSION, ...body };
    });
    server.use(post.handler, http.get('*/api/reading-books/', async () => {
      if (!saved) return HttpResponse.json([{ ...BOOK, status: 'want_to_read' }]);
      await new Promise((resolve) => { release = resolve; });
      return HttpResponse.json([BOOK]);
    }));
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('tab', { name: /Want to read/ }));
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    await user.type(within(dialog).getByLabelText('Pages read (optional)'), '2');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    await screen.findByText(/Reading saved for/);
    await waitFor(() => expect(release).toBeDefined());
    await user.click(screen.getByRole('tab', { name: /Finished/ }));
    await act(async () => { release(); });
    await waitFor(() => expect(screen.getByRole('tab', { name: /^Reading/ })).toHaveTextContent('1'));
    expect(post.calls).toHaveLength(1);
    expect(screen.getByRole('tab', { name: /Finished/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('logs the selected saved book, family date, listening time and a guided reflection; keeps its receipt when refresh fails', async () => {
    stub();
    let saved = false;
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, ({ body }) => { saved = true; return { ...SESSION, ...body, book_title: SECOND.title }; });
    server.use(post.handler, http.get('*/api/reading-sessions/', () => saved ? HttpResponse.json({ detail: 'History refresh unavailable.' }, { status: 500 }) : HttpResponse.json([])));
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('button', { name: `Log reading: ${SECOND.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    expect(within(dialog).getByLabelText('Which book?')).toHaveValue('13');
    expect(within(dialog).getByLabelText('Date read')).toHaveValue('2026-10-16');
    await selectDropdown(user, within(dialog).getByLabelText('How did you read?'), 'audiobook');
    await user.type(within(dialog).getByLabelText('Minutes (optional)'), '25');
    await user.type(within(dialog).getByLabelText('Chapter or section (optional)'), 'Chapter 5');
    await user.click(within(dialog).getByRole('button', { name: 'What surprised you?' }));
    await user.type(within(dialog).getByLabelText('What surprised you?'), 'The fox helped her.');
    await selectDropdown(user, within(dialog).getByLabelText('How was it? (optional)'), 'loved');
    expect(within(dialog).getByText(/You and your parents can read/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    expect(post.calls[0].body).toEqual({ book: 13, occurred_on: '2026-10-16', duration_minutes: 25, pages_read: 0, section: 'Chapter 5', reflection: 'The fox helped her.', format: 'audiobook', reaction: 'loved', client_request_id: expect.any(String) });
    expect(await screen.findByText(/Reading saved for/)).toHaveTextContent(SECOND.title);
    expect(await screen.findByText('History refresh unavailable.')).toBeInTheDocument();
    expect(screen.getByText('The fox helped her.')).toBeInTheDocument();
  });

  it('retries an uncertain POST with the exact same UUID and payload', async () => {
    stub();
    let attempt = 0;
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, ({ body }) => ++attempt === 1 ? HttpResponse.json({ detail: 'Temporary connection problem.' }, { status: 503 }) : { ...SESSION, ...body });
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    await user.type(within(dialog).getByLabelText('Your reading note (optional)'), 'I liked the island.');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    expect(await screen.findByText(/We could not confirm the save/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Your reading note (optional)')).toBeDisabled();
    await user.click(within(dialog).getByRole('button', { name: 'Retry save' }));
    await waitFor(() => expect(post.calls).toHaveLength(2));
    expect(post.calls[1].body).toEqual(post.calls[0].body);
    expect(post.calls[0].body.client_request_id).toMatch(/^[a-f0-9-]{36}$/);
    expect(await screen.findByText(/Reading saved for/)).toBeInTheDocument();
  });

  it('PATCHes a saved reading note and DELETEs the actual log after confirmation', async () => {
    stub({ sessions: [SESSION] });
    const patch = spyHandler('patch', /\/api\/reading-sessions\/42\/$/, ({ body }) => ({ ...SESSION, ...body }));
    const deletion = spyHandler('delete', /\/api\/reading-sessions\/42\/$/, new HttpResponse(null, { status: 204 }));
    server.use(patch.handler, deletion.handler);
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('button', { name: `Edit log: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit reading log' });
    await user.clear(within(dialog).getByLabelText('Pages read (optional)'));
    await user.type(within(dialog).getByLabelText('Pages read (optional)'), '17');
    await user.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    await waitFor(() => expect(patch.calls).toHaveLength(1));
    expect(patch.calls[0].body).toEqual({ occurred_on: '2026-10-15', duration_minutes: 20, pages_read: 17, section: SESSION.section, reflection: SESSION.reflection, format: 'print', reaction: 'liked' });
    await user.click(await screen.findByRole('button', { name: `Delete log: ${BOOK.title}` }));
    await user.click(within(await screen.findByRole('alertdialog', { name: 'Delete reading log?' })).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(deletion.calls).toHaveLength(1));
    expect(await screen.findByText('Reading log removed.')).toBeInTheDocument();
  });

  it('does not offer a blank log and never persists reflection drafts on the device', async () => {
    stub();
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('button', { name: 'Save reading' })).toBeDisabled();
    await user.type(within(dialog).getByLabelText('Your reading note (optional)'), 'A reflection stays in memory.');
    expect(within(dialog).getByRole('button', { name: 'Save reading' })).toBeEnabled();
    expect(JSON.stringify(localStorage)).not.toContain('A reflection stays in memory.');
  });
});

describe('Daily reading rewards', () => {
  it('shows server progress and rewards only after a confirmed listening log, then refreshes shared RPG state', async () => {
    stub();
    let saved = false;
    let release;
    const rewardedSession = { ...SESSION, occurred_on: SUMMARY.today, duration_minutes: 6, pages_read: 0, reflection: '', format: 'audiobook', reading_reward: REWARD };
    const response = new HttpResponse(new ReadableStream({ start(controller) {
      release = () => {
        saved = true;
        controller.enqueue(new TextEncoder().encode(JSON.stringify(rewardedSession)));
        controller.close();
      };
    } }), { headers: { 'Content-Type': 'application/json' } });
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, response);
    server.use(post.handler,
      http.get('*/api/reading-sessions/', () => HttpResponse.json(saved ? [rewardedSession] : [])),
      http.get('*/api/reading/summary/', () => HttpResponse.json({ ...SUMMARY, reading_adventure: saved ? { ...ADVENTURE, minutes_credited: 10, remaining_minutes: 0, earned: true, xp_awarded: 30, coins_awarded: 10 } : ADVENTURE })),
    );
    const refresh = vi.fn();
    const { user } = renderWithProviders(<PulseContext.Provider value={{ pulse: null, refresh }}><Reading /></PulseContext.Provider>);
    const adventure = await screen.findByRole('region', { name: 'Today’s reading reward' });
    expect(within(adventure).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '4');
    expect(within(adventure).getByText(/6 more minutes today/)).toBeInTheDocument();
    expect(within(adventure).getByText('15 base Reading Comprehension XP')).toBeInTheDocument();
    expect(within(adventure).getByText('5 base Coins')).toBeInTheDocument();
    expect(within(adventure).getByText(/activity streak and gives a chance of loot/)).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    expect(within(dialog).getByText(/Pages, chapters and notes can still be saved without minutes/)).toBeInTheDocument();
    await selectDropdown(user, within(dialog).getByLabelText('How did you read?'), 'audiobook');
    await user.type(within(dialog).getByLabelText('Minutes (optional)'), '6');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    expect(post.calls[0].body).toEqual({ book: 12, occurred_on: SUMMARY.today, duration_minutes: 6, pages_read: 0, section: '', reflection: '', format: 'audiobook', reaction: '', client_request_id: expect.any(String) });
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.queryByText(/Earned today: 30/)).toBeNull();
    await act(async () => { release(); });
    expect(await screen.findByText(/Daily reading reward recorded: 30 Reading Comprehension XP and 10 Coins/)).toBeInTheDocument();
    expect(await within(adventure).findByText('Earned today: 30 Reading Comprehension XP and 10 Coins.')).toBeInTheDocument();
    expect(within(adventure).getByRole('progressbar')).toHaveAttribute('aria-valuenow', '10');
    expect(within(await screen.findByRole('article', { name: `Reading log: ${BOOK.title}` })).getByText(/Daily reading reward: 30 Reading Comprehension XP · 10 Coins/)).toBeInTheDocument();
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('retains one recorded reward through an uncertain retry and later correction without inventing another award', async () => {
    stub();
    const rewardedSession = { ...SESSION, occurred_on: SUMMARY.today, duration_minutes: 10, reading_reward: REWARD };
    let attempt = 0;
    let saved = false;
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, () => {
      if (++attempt === 1) return HttpResponse.json({ detail: 'Save confirmation interrupted.' }, { status: 503 });
      saved = true;
      return rewardedSession;
    });
    const patch = spyHandler('patch', /\/api\/reading-sessions\/42\/$/, ({ body }) => ({ ...rewardedSession, ...body }));
    server.use(post.handler, patch.handler,
      http.get('*/api/reading-sessions/', () => HttpResponse.json(saved ? [rewardedSession] : [])),
      http.get('*/api/reading/summary/', () => HttpResponse.json({ ...SUMMARY, reading_adventure: { ...ADVENTURE, minutes_credited: 0, remaining_minutes: 10 } })),
    );
    const refresh = vi.fn();
    const { user } = renderWithProviders(<PulseContext.Provider value={{ pulse: null, refresh }}><Reading /></PulseContext.Provider>);
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    let dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    await user.type(within(dialog).getByLabelText('Minutes (optional)'), '10');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    expect(await screen.findByText(/We could not confirm the save/)).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.queryByText(/Daily reading reward recorded:/)).toBeNull();
    await user.click(within(dialog).getByRole('button', { name: 'Retry save' }));
    expect(await screen.findByText(/Daily reading reward recorded: 30 Reading Comprehension XP and 10 Coins/)).toBeInTheDocument();
    expect(post.calls).toHaveLength(2);
    expect(post.calls[1].body).toEqual(post.calls[0].body);
    expect(refresh).toHaveBeenCalledTimes(1);
    await user.click(await screen.findByRole('button', { name: `Edit log: ${BOOK.title}` }));
    dialog = await screen.findByRole('dialog', { name: 'Edit reading log' });
    expect(within(dialog).getByText(/Editing a log does not add reward minutes/)).toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText('Minutes (optional)'));
    await user.type(within(dialog).getByLabelText('Minutes (optional)'), '30');
    await user.click(within(dialog).getByRole('button', { name: 'Save changes' }));
    expect(await screen.findByText(/Reading changes saved for/)).toHaveTextContent('30 Reading Comprehension XP and 10 Coins');
    expect(patch.calls).toHaveLength(1);
    expect(patch.calls[0].body).toEqual({ occurred_on: SUMMARY.today, duration_minutes: 30, pages_read: 14, section: SESSION.section, reflection: SESSION.reflection, format: 'print', reaction: 'liked' });
    expect(post.calls).toHaveLength(2);
    expect(refresh).toHaveBeenCalledTimes(2);
    expect(screen.queryByText(/60 Reading Comprehension XP/)).toBeNull();
  });

  it('explains past dates, keeps pages-only logs valid, and shows no reward when the server returns none', async () => {
    stub();
    server.use(http.get('*/api/reading/summary/', () => HttpResponse.json({ ...SUMMARY, reading_adventure: ADVENTURE })));
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, ({ body }) => ({ ...SESSION, ...body, reading_reward: null }));
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    await user.clear(within(dialog).getByLabelText('Date read'));
    await user.type(within(dialog).getByLabelText('Date read'), '2026-10-15');
    expect(within(dialog).getByText(/Earlier reading belongs in your history/)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText('Pages read (optional)'), '12');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    expect(await screen.findByText(/Reading saved for/)).toBeInTheDocument();
    expect(post.calls).toHaveLength(1);
    expect(post.calls[0].body).toMatchObject({ occurred_on: '2026-10-15', duration_minutes: 0, pages_read: 12, reflection: '' });
    expect(screen.queryByText(/Daily reading reward recorded:/)).toBeNull();
    expect(screen.getByRole('progressbar', { name: 'Today’s reading reward minutes' })).toHaveAttribute('aria-valuenow', '4');
  });

  it('explains that another new log can be saved after the daily reward has been earned', async () => {
    stub();
    server.use(http.get('*/api/reading/summary/', () => HttpResponse.json({ ...SUMMARY, reading_adventure: { ...ADVENTURE, minutes_credited: 10, remaining_minutes: 0, earned: true, xp_awarded: 30, coins_awarded: 10 } })));
    const { user } = renderWithProviders(<Reading />);
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    expect(within(dialog).getByText(/Today’s reading reward is already earned/)).toBeInTheDocument();
    await user.type(within(dialog).getByLabelText('Chapter or section (optional)'), 'The dragon’s return');
    expect(within(dialog).getByRole('button', { name: 'Save reading' })).toBeEnabled();
  });

  it('refreshes the household day and reward progress on the shared heartbeat without awarding anything', async () => {
    stub();
    let nextDay = false;
    server.use(http.get('*/api/reading/summary/', () => HttpResponse.json({ ...SUMMARY, today: nextDay ? '2026-10-17' : SUMMARY.today, reading_adventure: nextDay ? { ...ADVENTURE, day: '2026-10-17', minutes_credited: 0, remaining_minutes: 10 } : { ...ADVENTURE, minutes_credited: 10, remaining_minutes: 0, earned: true, xp_awarded: 30, coins_awarded: 10 } })));
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, {});
    server.use(post.handler);
    const { user, beat } = renderWithProviders(<Reading />);
    expect(await screen.findByText('Earned today: 30 Reading Comprehension XP and 10 Coins.')).toBeInTheDocument();
    nextDay = true;
    beat({ header: { coin_balance: 10 } });
    expect(await screen.findByText(/10 more minutes today/)).toBeInTheDocument();
    expect(screen.queryByText('Earned today: 30 Reading Comprehension XP and 10 Coins.')).toBeNull();
    await user.click(screen.getByRole('button', { name: `Log reading: ${BOOK.title}` }));
    expect(within(await screen.findByRole('dialog')).getByLabelText('Date read')).toHaveValue('2026-10-17');
    expect(post.calls).toHaveLength(0);
  });

  it('keeps the saved award when summary refresh fails and hides outdated eligibility', async () => {
    stub();
    let saved = false;
    server.use(http.get('*/api/reading/summary/', () => saved ? HttpResponse.json({ detail: 'Reward progress unavailable.' }, { status: 503 }) : HttpResponse.json({ ...SUMMARY, reading_adventure: ADVENTURE })));
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, ({ body }) => {
      saved = true;
      return { ...SESSION, ...body, reading_reward: REWARD };
    });
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />);
    expect(await screen.findByRole('region', { name: 'Today’s reading reward' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Minutes (optional)'), '6');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    expect(await screen.findByText(/Daily reading reward recorded: 30 Reading Comprehension XP and 10 Coins/)).toBeInTheDocument();
    expect(await screen.findByText(/Reading totals unavailable. Reward progress unavailable/)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Today’s reading reward' })).toBeNull();
    expect(post.calls).toHaveLength(1);
  });

  it('discards a late reward response after an account change and never refreshes the replacement account from that save', async () => {
    stub();
    let release;
    const response = new HttpResponse(new ReadableStream({ start(controller) {
      release = () => {
        controller.enqueue(new TextEncoder().encode(JSON.stringify({ ...SESSION, reading_reward: REWARD })));
        controller.close();
      };
    } }), { headers: { 'Content-Type': 'application/json' } });
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, response);
    server.use(post.handler);
    const refresh = vi.fn();
    function Harness() {
      const { setUser } = useAuth();
      return <PulseContext.Provider value={{ pulse: null, refresh }}><button onClick={() => { localStorage.setItem('abby_auth_token', 'replacement-token'); setUser(buildUser({ id: 8 })); }}>Switch account</button><Reading /></PulseContext.Provider>;
    }
    const { user } = renderWithProviders(<Harness />);
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    await user.type(within(dialog).getByLabelText('Minutes (optional)'), '10');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    server.use(http.get('*/api/reading-books/', () => HttpResponse.json([{ ...SECOND, user: 8 }])), http.get('*/api/reading-sessions/', () => HttpResponse.json([])));
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    expect(await screen.findByRole('article', { name: SECOND.title })).toBeInTheDocument();
    await act(async () => { release(); });
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.queryByText(/Daily reading reward recorded:/)).toBeNull();
    expect(screen.queryByRole('article', { name: `Reading log: ${BOOK.title}` })).toBeNull();
    expect(post.calls).toHaveLength(1);
  });
});

describe('Reading discovery and family context', () => {
  it('changes recommendation topics and explicitly saves a suggestion to want to read', async () => {
    stub({ books: [] });
    const reads = [];
    server.use(http.get('*/api/reading/recommendations/', ({ request }) => {
      reads.push(new URL(request.url).searchParams.get('interest'));
      return HttpResponse.json({ results: [{ ...SUGGESTION, age_max: null }], basis: 'Books to explore together.' });
    }));
    const post = spyHandler('post', /\/api\/reading-books\/$/, ({ body }) => ({ ...BOOK, ...body }));
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />);
    expect(await screen.findByText('Ages 8+')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /About this book/ })).toHaveAttribute('href', SUGGESTION.source_url);
    await selectDropdown(user, screen.getByLabelText('Explore a topic'), 'science');
    await waitFor(() => expect(reads).toEqual([null, 'science']));
    await user.click(screen.getByRole('button', { name: 'Save to want to read' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add a book' });
    expect(within(dialog).getByLabelText('Book title')).toHaveValue(BOOK.title);
    expect(within(dialog).getByLabelText('Shelf')).toHaveValue('want_to_read');
    await user.click(within(dialog).getByRole('button', { name: 'Save book' }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    expect(post.calls[0].body).toMatchObject({ title: BOOK.title, author: BOOK.author, status: 'want_to_read', interests: BOOK.interests });
  });

  it('scopes every parent read and book create to the verified selected child', async () => {
    stub({ parent: true, books: [] });
    const targets = [];
    for (const endpoint of ['reading-books', 'reading-sessions', 'reading/summary', 'reading/recommendations']) server.use(http.get(`*/api/${endpoint}/`, ({ request }) => {
      targets.push(new URL(request.url).searchParams.get('user_id'));
      return HttpResponse.json(endpoint === 'reading/summary' ? SUMMARY : { results: [], next: null });
    }));
    const post = spyHandler('post', /\/api\/reading-books\/$/, ({ body }) => ({ ...body, id: 88, user: 8 }));
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />, { route: '/quests?tab=reading&child=8' });
    expect(await screen.findByLabelText('Viewing')).toHaveValue('8');
    const dialog = await addBook(user);
    await user.type(within(dialog).getByLabelText('Book title'), 'Ben’s book');
    await user.click(within(dialog).getByRole('button', { name: 'Save book' }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    expect(post.calls[0].body.user_id).toBe(8);
    expect(targets.length).toBeGreaterThanOrEqual(4);
    expect(targets.every((target) => target === '8')).toBe(true);
  });

  it('includes the selected child in a parent session POST and accepts a chapter without numbers', async () => {
    stub({ parent: true });
    const post = spyHandler('post', /\/api\/reading-sessions\/$/, ({ body }) => ({ ...SESSION, ...body }));
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />, { route: '/quests?tab=reading&child=7' });
    await user.click(await screen.findByRole('button', { name: `Log reading: ${BOOK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Log your reading' });
    await user.type(within(dialog).getByLabelText('Chapter or section (optional)'), 'Finished chapter 3');
    await user.click(within(dialog).getByRole('button', { name: 'Save reading' }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    expect(post.calls[0].body).toMatchObject({ book: 12, user_id: 7, duration_minutes: 0, pages_read: 0, section: 'Finished chapter 3' });
  });

  it('follows shelf and history pages while keeping the verified reader fixed', async () => {
    stub({ parent: true });
    const requests = [];
    server.use(
      http.get('*/api/reading-books/', ({ request }) => {
        const url = new URL(request.url);
        requests.push([url.pathname, url.searchParams.get('user_id'), url.searchParams.get('page')]);
        return HttpResponse.json(url.searchParams.get('page') === '2' ? { results: [SECOND], next: null } : { results: [BOOK], next: 'https://different.invalid/api/reading-books/?page=2&user_id=99' });
      }),
      http.get('*/api/reading-sessions/', ({ request }) => {
        const url = new URL(request.url);
        requests.push([url.pathname, url.searchParams.get('user_id'), url.searchParams.get('page')]);
        return HttpResponse.json(url.searchParams.get('page') === '2' ? { results: [{ ...SESSION, id: 43, reflection: 'Earlier reading note.' }], next: null } : { results: [SESSION], next: 'https://different.invalid/api/reading-sessions/?page=2&user_id=99' });
      }),
    );
    const { user } = renderWithProviders(<Reading />, { route: '/quests?tab=reading&child=7' });
    expect(await screen.findByRole('article', { name: SECOND.title })).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Show earlier reading' }));
    expect(await screen.findByText('Earlier reading note.')).toBeInTheDocument();
    expect(requests).toContainEqual(['/api/reading-books/', '7', '2']);
    expect(requests).toContainEqual(['/api/reading-sessions/', '7', '2']);
    expect(requests.every(([, target]) => target === '7')).toBe(true);
    expect(screen.getByText(SESSION.reflection)).toBeInTheDocument();
  });

  it('hides sibling data and fences a late history response after changing the selected child', async () => {
    stub({ parent: true });
    let release;
    server.use(
      http.get('*/api/reading-books/', ({ request }) => HttpResponse.json(new URL(request.url).searchParams.get('user_id') === '8' ? [{ ...SECOND, user: 8 }] : [BOOK, { ...SECOND, user: 8 }])),
      http.get('*/api/reading-sessions/', async ({ request }) => {
        if (new URL(request.url).searchParams.get('user_id') === '7') {
          await new Promise((resolve) => { release = resolve; });
          return HttpResponse.json([SESSION]);
        }
        return HttpResponse.json([{ ...SESSION, id: 55, user: 8, book: 13, book_title: SECOND.title, reflection: 'Ben’s reflection.' }]);
      }),
    );
    const { user } = renderWithProviders(<Reading />, { route: '/quests?tab=reading&child=7' });
    await screen.findByRole('article', { name: BOOK.title });
    expect(screen.queryByRole('article', { name: SECOND.title })).toBeNull();
    await waitFor(() => expect(release).toBeDefined());
    await selectDropdown(user, screen.getByLabelText('Viewing'), '8');
    expect(await screen.findByText('Ben’s reflection.')).toBeInTheDocument();
    await act(async () => { release(); });
    expect(screen.queryByText(SESSION.reflection)).toBeNull();
    expect(screen.getByRole('article', { name: SECOND.title })).toBeInTheDocument();
  });

  it('clears old books, notes and open drafts when the account credential changes', async () => {
    stub({ sessions: [SESSION] });
    function Harness() {
      const { setUser } = useAuth();
      return <><button onClick={() => { localStorage.setItem('abby_auth_token', 'replacement-token'); setUser(buildUser({ id: 8 })); }}>Switch account</button><Reading /></>;
    }
    const { user } = renderWithProviders(<Harness />);
    await screen.findByText(SESSION.reflection);
    await user.click(screen.getByRole('button', { name: `Log reading: ${BOOK.title}` }));
    await user.type(screen.getByLabelText('Your reading note (optional)'), 'Old account draft.');
    server.use(http.get('*/api/reading-books/', () => HttpResponse.json([{ ...SECOND, user: 8 }])), http.get('*/api/reading-sessions/', () => HttpResponse.json([])));
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    expect(await screen.findByRole('article', { name: SECOND.title })).toBeInTheDocument();
    expect(screen.queryByText(SESSION.reflection)).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByDisplayValue('Old account draft.')).toBeNull();
  });

  it('shows source-specific failures with retry, without calling a failed read an empty shelf', async () => {
    stub();
    let failed = true;
    server.use(http.get('*/api/reading-books/', () => failed ? HttpResponse.json({ detail: 'Bookshelf unavailable.' }, { status: 503 }) : HttpResponse.json([BOOK])));
    const { user } = renderWithProviders(<Reading />);
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Bookshelf unavailable.');
    expect(screen.queryByText('Your next story starts here.')).toBeNull();
    failed = false;
    await user.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('article', { name: BOOK.title })).toBeInTheDocument();
  });
});
