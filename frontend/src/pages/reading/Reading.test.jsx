import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { useAuth } from '../../hooks/useApi';
import { renderWithProviders, screen, waitFor, within, act } from '../../test/render';
import { server } from '../../test/server';
import { buildUser, buildParent } from '../../test/factories';
import { selectDropdown } from '../../test/selectDropdown';
import { spyHandler } from '../../test/spy';
import Reading from './index';

const BOOK = { id: 12, user: 7, title: 'The Wild Robot', author: 'Peter Brown', status: 'reading', interests: ['animals', 'science'] };
const SECOND = { ...BOOK, id: 13, title: 'A Different Story', author: 'Another Author' };
const SESSION = { id: 42, user: 7, book: 12, book_title: BOOK.title, book_author: BOOK.author, occurred_on: '2026-10-15', duration_minutes: 20, pages_read: 14, section: 'Chapter 2', reflection: 'Roz learned to listen.', format: 'print', reaction: 'liked' };
const SUMMARY = { books_total: 2, books_finished: 1, sessions_total: 4, total_minutes: 85, total_pages: 60, today: '2026-10-16', timezone: 'America/Phoenix' };
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
