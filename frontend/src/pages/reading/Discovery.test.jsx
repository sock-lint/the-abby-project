import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { useAuth } from '../../hooks/useApi';
import { renderWithProviders, screen, waitFor, within, fireEvent, act } from '../../test/render';
import { server } from '../../test/server';
import { buildUser, buildParent } from '../../test/factories';
import { selectDropdown } from '../../test/selectDropdown';
import { spyHandler } from '../../test/spy';
import Reading from './index';

const PICK = {
  id: 'wild-robot-escapes', title: 'The Wild Robot Escapes', author: 'Peter Brown', interests: ['animals', 'science'],
  age_min: 8, age_max: 12, description: 'Roz finds a way home.', source_url: 'https://www.hachettebookgroup.com/a-book/',
  isbn: '9780316479264', page_count: 288, formats: ['print', 'ebook', 'audiobook'], moods: ['exciting'], styles: ['illustrated', 'short_chapters'], themes: ['nature'],
  series: { id: 'wild-robot', title: 'The Wild Robot', position: 2 }, cover_url: 'https://covers.openlibrary.org/b/isbn/9780316479264-M.jpg?default=false',
  reason: 'Continue The Wild Robot with book 2.', reason_kind: 'series',
};
const OTHER = { ...PICK, id: 'dragons', title: 'Dragon Days', author: 'A. Writer', series: null };
const SUMMARY = { books_total: 0, books_finished: 0, sessions_total: 0, total_minutes: 0, total_pages: 0, today: '2026-10-17', timezone: 'America/Phoenix' };
const FAMILY = { id: 51, user: 7, suggested_by: { id: 90, display_name: 'Morgan' }, catalog_id: PICK.id, catalog_entry: PICK, message: 'I thought you would love another adventure with Roz.', status: 'pending', on_shelf: false };
function stub({ parent = false, picks = [PICK], family = [], books = [] } = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(parent ? buildParent({ id: 90, family: { id: 1 } }) : buildUser({ id: 7 }))),
    http.get('*/api/children/', () => HttpResponse.json([{ id: 7, username: 'abby' }, { id: 8, username: 'ben' }])),
    http.get('*/api/reading-books/', () => HttpResponse.json({ count: books.length, next: null, results: books })),
    http.get('*/api/reading-sessions/', () => HttpResponse.json([])),
    http.get('*/api/reading/summary/', () => HttpResponse.json(SUMMARY)),
    http.get('*/api/reading/recommendations/', () => HttpResponse.json({ results: picks, basis: 'Books picked for you.', total: picks.length, has_more: false, rotation: 0 })),
    http.get('*/api/reading-family-suggestions/', () => HttpResponse.json({ count: family.length, next: null, results: family })),
  );
}
const suggestedCard = () => screen.findByRole('article', { name: `Suggested book: ${PICK.title}` });

describe('Reading discovery', () => {
  it('shows covers, a spoiler-free hook, formats, pages, series order, and encoded library searches with an image fallback', async () => {
    stub();
    renderWithProviders(<Reading />);
    const card = await suggestedCard();
    const image = within(card).getByRole('img', { name: `Cover of ${PICK.title}` });
    expect(image).toHaveAttribute('loading', 'lazy');
    expect(image).toHaveAttribute('referrerpolicy', 'no-referrer');
    expect(within(card).getByText('288 pages')).toBeInTheDocument();
    expect(within(card).getByText('Book 2 in The Wild Robot')).toBeInTheDocument();
    expect(within(card).getByText(PICK.description)).toBeInTheDocument();
    expect(within(card).getByText('Audiobook')).toBeInTheDocument();
    expect(within(card).getByText('Short chapters')).toBeInTheDocument();
    expect(within(card).getByText(PICK.reason)).toBeInTheDocument();
    expect(within(card).getByText('Continue a series')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show different books' })).toBeDisabled();
    expect(screen.getByText('All matching books are shown. Try a different filter to explore more.')).toBeInTheDocument();
    const link = within(card).getByRole('link', { name: /Find at a library/ });
    expect(new URL(link.href).searchParams.get('q')).toBe(`${PICK.title} ${PICK.author}`);
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(within(card).getByRole('link', { name: /About this book/ })).toHaveAttribute('href', PICK.source_url);
    fireEvent.error(image);
    expect(within(card).queryByRole('img')).toBeNull();
    expect(within(card).getByText(`Cover unavailable for ${PICK.title}`)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Find your next read' }).compareDocumentPosition(screen.getByRole('region', { name: 'Reading history' })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('sends every discovery filter, search, refresh and book-specific matching to the server and resets them', async () => {
    stub();
    const reads = [];
    server.use(http.get('*/api/reading/recommendations/', ({ request }) => {
      reads.push(Object.fromEntries([...new URL(request.url).searchParams].filter(([key]) => key !== '_abby_session')));
      return HttpResponse.json({ results: [PICK], basis: 'Picked for you.' });
    }));
    const { user } = renderWithProviders(<Reading />);
    await suggestedCard();
    await selectDropdown(user, screen.getByLabelText('Explore a topic'), 'science');
    await selectDropdown(user, screen.getByLabelText('What sounds good today?'), 'exciting');
    await user.click(screen.getByText('More ways to choose'));
    await selectDropdown(user, screen.getByLabelText('Reading style'), 'short_chapters');
    await selectDropdown(user, screen.getByLabelText('Book format'), 'audiobook');
    await selectDropdown(user, screen.getByLabelText('Book length'), 'medium');
    await selectDropdown(user, screen.getByLabelText('Explore a theme'), 'nature');
    await user.type(screen.getByLabelText('Search books'), 'Roz');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(reads.at(-1)).toEqual({ interest: 'science', mood: 'exciting', style: 'short_chapters', book_format: 'audiobook', length: 'medium', theme: 'nature', q: 'Roz', rotation: '0' }));
    await user.click(screen.getByRole('button', { name: 'Show different books' }));
    await waitFor(() => expect(reads.at(-1).rotation).toBe('1'));
    await user.click(screen.getByRole('button', { name: `More like this: ${PICK.title}` }));
    await waitFor(() => expect(reads.at(-1)).toMatchObject({ similar_to: PICK.id, rotation: '0' }));
    await user.click(screen.getByRole('button', { name: 'Reset filters' }));
    await waitFor(() => expect(reads.at(-1)).toEqual({ rotation: '0' }));
    expect(screen.getByLabelText('Search books')).toHaveValue('');
    expect(screen.queryByRole('button', { name: 'Clear similar book' })).toBeNull();
  });

  it('can find more like a specific saved book and keeps its server-confirmed series identity', async () => {
    stub({ books: [{ id: 3, user: 7, title: PICK.title, author: PICK.author, interests: [], status: 'reading', catalog_entry: PICK }] });
    const reads = [];
    server.use(http.get('*/api/reading/recommendations/', ({ request }) => {
      reads.push(new URL(request.url).searchParams.get('similar_to'));
      return HttpResponse.json({ results: [], basis: 'Something similar.' });
    }));
    const { user } = renderWithProviders(<Reading />);
    const saved = await screen.findByRole('article', { name: PICK.title });
    expect(within(saved).getByText('Book 2 in The Wild Robot')).toBeInTheDocument();
    await user.click(within(saved).getByRole('button', { name: `More like this: ${PICK.title}` }));
    await waitFor(() => expect(reads.at(-1)).toBe(PICK.id));
  });

  it.each(['not_interested', 'already_read'])('records %s feedback with undo without creating a reading log', async (choice) => {
    stub();
    const post = spyHandler('post', /\/api\/reading\/discovery-feedback\/$/, ({ body }) => body);
    const log = spyHandler('post', /\/api\/reading-sessions\/$/, {});
    const shelf = spyHandler('post', /\/api\/reading-books\/$/, {});
    server.use(post.handler, log.handler, shelf.handler);
    const { user } = renderWithProviders(<Reading />);
    const card = await suggestedCard();
    await user.click(within(card).getByRole('button', { name: `${choice === 'already_read' ? 'Already read' : 'Not interested'}: ${PICK.title}` }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    expect(post.calls[0].body).toEqual({ catalog_id: PICK.id, choice });
    await waitFor(() => expect(screen.queryByRole('article', { name: `Suggested book: ${PICK.title}` })).toBeNull());
    await user.click(screen.getByRole('button', { name: 'Undo' }));
    await suggestedCard();
    expect(post.calls).toHaveLength(2);
    expect(post.calls[1].body).toEqual({ catalog_id: PICK.id, choice: '' });
    expect(log.calls).toHaveLength(0);
    expect(shelf.calls).toHaveLength(0);
  });

  it('retries the identical idempotent feedback after an uncertain response, scoped to the selected child', async () => {
    stub({ parent: true });
    let attempt = 0;
    const post = spyHandler('post', /\/api\/reading\/discovery-feedback\/$/, ({ body }) => ++attempt === 1 ? HttpResponse.json({ detail: 'Confirmation interrupted.' }, { status: 503 }) : body);
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />, { route: '/quests?tab=reading&child=8' });
    const card = await suggestedCard();
    await user.click(within(card).getByRole('button', { name: `Not interested: ${PICK.title}` }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Retry to confirm this change.');
    expect(within(card).getByRole('button', { name: `Already read: ${PICK.title}` })).toBeDisabled();
    await user.click(within(alert).getByRole('button', { name: 'Try again' }));
    await screen.findByRole('button', { name: 'Undo' });
    expect(post.calls.map((call) => call.body)).toEqual([{ user_id: 8, catalog_id: PICK.id, choice: 'not_interested' }, { user_id: 8, catalog_id: PICK.id, choice: 'not_interested' }]);
  });

  it('shows an honest empty result and keeps family failures separate from ordinary discovery', async () => {
    stub({ picks: [] });
    server.use(http.get('*/api/reading-family-suggestions/', () => HttpResponse.json({ detail: 'Family suggestions unavailable.' }, { status: 503 })));
    renderWithProviders(<Reading />);
    expect(await screen.findByText('No matching books right now. Try another topic or reset the filters.')).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent('Family suggestions unavailable.');
    expect(screen.getByRole('button', { name: 'Show different books' })).toBeDisabled();
    expect(screen.getByText('Your next story starts here.')).toBeInTheDocument();
  });
});

describe('Family book suggestions', () => {
  it('sends a parent’s note with the verified child and one UUID, retaining the exact payload on uncertain retry', async () => {
    stub({ parent: true });
    let attempt = 0;
    let sent;
    const post = spyHandler('post', /\/api\/reading-family-suggestions\/$/, ({ body }) => {
      if (++attempt === 1) return HttpResponse.json({ detail: 'Confirmation interrupted.' }, { status: 503 });
      sent = { ...FAMILY, ...body, user: body.user_id };
      return sent;
    });
    const book = spyHandler('post', /\/api\/reading-books\/$/, {});
    server.use(post.handler, book.handler, http.get('*/api/reading-family-suggestions/', ({ request }) => HttpResponse.json({ results: sent && String(sent.user) === new URL(request.url).searchParams.get('user_id') ? [sent] : [], next: null })));
    const { user } = renderWithProviders(<Reading />, { route: '/quests?tab=reading&child=8' });
    await user.click(within(await suggestedCard()).getByRole('button', { name: `Send a suggestion: ${PICK.title}` }));
    const dialog = await screen.findByRole('dialog', { name: 'Send a book suggestion' });
    await user.type(within(dialog).getByLabelText('Personal note (optional)'), FAMILY.message);
    await user.click(within(dialog).getByRole('button', { name: 'Send suggestion' }));
    expect(await screen.findByText(/We could not confirm the suggestion/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Personal note (optional)')).toBeDisabled();
    await user.click(within(dialog).getByRole('button', { name: 'Retry suggestion' }));
    expect(await screen.findByText('Suggestion sent. Your child can choose whether to save it.')).toBeInTheDocument();
    expect(post.calls).toHaveLength(2);
    expect(post.calls[0].body).toEqual({ catalog_id: PICK.id, user_id: 8, message: FAMILY.message, client_request_id: expect.stringMatching(/^[a-f0-9-]{36}$/) });
    expect(post.calls[1].body).toEqual(post.calls[0].body);
    expect(book.calls).toHaveLength(0);
    const shared = await screen.findByRole('article', { name: `Family suggestion: ${PICK.title}` });
    expect(within(shared).getByText('Suggested by Morgan')).toBeInTheDocument();
    expect(within(shared).getByText(FAMILY.message)).toBeInTheDocument();
  });

  it('keeps suggestions off the child’s shelf until the child explicitly saves and submits a book', async () => {
    stub({ picks: [], family: [FAMILY] });
    let saved;
    const post = spyHandler('post', /\/api\/reading-books\/$/, ({ body }) => { saved = { ...body, id: 12, user: 7, catalog_entry: PICK }; return saved; });
    server.use(post.handler, http.get('*/api/reading-books/', () => HttpResponse.json(saved ? [saved] : [])), http.get('*/api/reading-family-suggestions/', () => HttpResponse.json({ results: [{ ...FAMILY, on_shelf: Boolean(saved) }] })));
    const { user } = renderWithProviders(<Reading />);
    const card = await screen.findByRole('article', { name: `Family suggestion: ${PICK.title}` });
    expect(within(card).getByText('Suggested by Morgan')).toBeInTheDocument();
    expect(post.calls).toHaveLength(0);
    await user.click(within(card).getByRole('button', { name: 'Save to want to read' }));
    const dialog = await screen.findByRole('dialog', { name: 'Add a book' });
    expect(within(dialog).getByLabelText('Book title')).toHaveValue(PICK.title);
    expect(post.calls).toHaveLength(0);
    await user.click(within(dialog).getByRole('button', { name: 'Save book' }));
    expect(await screen.findByText(/saved to Want to read/)).toBeInTheDocument();
    expect(post.calls).toHaveLength(1);
    expect(post.calls[0].body).toEqual({ title: PICK.title, author: PICK.author, status: 'want_to_read', interests: PICK.interests, client_request_id: expect.stringMatching(/^[a-f0-9-]{36}$/) });
    expect(await within(card).findByRole('button', { name: 'On your shelf' })).toBeDisabled();
  });

  it('dismisses a family suggestion with an exact PATCH without touching the shelf', async () => {
    stub({ family: [FAMILY] });
    const patch = spyHandler('patch', /\/api\/reading-family-suggestions\/51\/$/, { ...FAMILY, status: 'dismissed' });
    const book = spyHandler('post', /\/api\/reading-books\/$/, {});
    server.use(patch.handler, book.handler);
    const { user } = renderWithProviders(<Reading />);
    const card = await screen.findByRole('article', { name: `Family suggestion: ${PICK.title}` });
    await user.click(within(card).getByRole('button', { name: `Dismiss suggestion: ${PICK.title}` }));
    expect(await screen.findByText('Family suggestion dismissed.')).toBeInTheDocument();
    expect(patch.calls).toHaveLength(1);
    expect(patch.calls[0].body).toEqual({ status: 'dismissed' });
    expect(screen.queryByRole('article', { name: `Family suggestion: ${PICK.title}` })).toBeNull();
    expect(book.calls).toHaveLength(0);
  });

  it('shows parents when a child has saved a family suggestion, using the confirmed server response', async () => {
    stub({ parent: true, family: [{ ...FAMILY, on_shelf: true }] });
    renderWithProviders(<Reading />, { route: '/quests?tab=reading&child=7' });
    const card = await screen.findByRole('article', { name: `Family suggestion: ${PICK.title}` });
    expect(within(card).getByText('Saved to their shelf')).toBeInTheDocument();
    expect(within(card).queryByRole('button', { name: 'Save to want to read' })).toBeNull();
  });

  it('maps a rejected note to its field and keeps the draft editable', async () => {
    stub({ parent: true });
    const post = spyHandler('post', /\/api\/reading-family-suggestions\/$/, HttpResponse.json({ message: ['Please shorten this note.'] }, { status: 400 }));
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />);
    await user.click(within(await suggestedCard()).getByRole('button', { name: `Send a suggestion: ${PICK.title}` }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Personal note (optional)'), 'Keep this draft');
    await user.click(within(dialog).getByRole('button', { name: 'Send suggestion' }));
    expect(await screen.findByText('Please shorten this note.')).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Personal note (optional)')).toHaveValue('Keep this draft');
    expect(within(dialog).getByLabelText('Personal note (optional)')).toBeEnabled();
    expect(post.calls).toHaveLength(1);
  });

  it('fences a late suggestion save and clears its personal draft when the selected child changes', async () => {
    stub({ parent: true });
    let release;
    const response = new HttpResponse(new ReadableStream({ start(controller) { release = () => { controller.enqueue(new TextEncoder().encode(JSON.stringify(FAMILY))); controller.close(); }; } }), { headers: { 'Content-Type': 'application/json' } });
    const post = spyHandler('post', /\/api\/reading-family-suggestions\/$/, response);
    server.use(post.handler);
    const { user } = renderWithProviders(<Reading />, { route: '/quests?tab=reading&child=7' });
    await user.click(within(await suggestedCard()).getByRole('button', { name: `Send a suggestion: ${PICK.title}` }));
    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText('Personal note (optional)'), 'Only for Abby.');
    await user.click(within(dialog).getByRole('button', { name: 'Send suggestion' }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    await selectDropdown(user, screen.getByLabelText('Viewing'), '8');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    await act(async () => { release(); });
    expect(screen.queryByText('Suggestion sent. Your child can choose whether to save it.')).toBeNull();
    await user.click(within(await suggestedCard()).getByRole('button', { name: `Send a suggestion: ${PICK.title}` }));
    expect(screen.getByLabelText('Personal note (optional)')).toHaveValue('');
    expect(post.calls[0].body.user_id).toBe(7);
  });

  it('discards late family reads and discovery feedback when the account credential changes', async () => {
    stub();
    let releaseFamily;
    let releaseFeedback;
    const post = spyHandler('post', /\/api\/reading\/discovery-feedback\/$/, new HttpResponse(new ReadableStream({ start(controller) { releaseFeedback = () => { controller.enqueue(new TextEncoder().encode(JSON.stringify({ catalog_id: PICK.id, choice: 'not_interested' }))); controller.close(); }; } }), { headers: { 'Content-Type': 'application/json' } }));
    server.use(post.handler, http.get('*/api/reading-family-suggestions/', async () => {
      await new Promise((resolve) => { releaseFamily = resolve; });
      return HttpResponse.json({ results: [FAMILY] });
    }));
    function Harness() {
      const { setUser } = useAuth();
      return <><button onClick={() => { localStorage.setItem('abby_auth_token', 'replacement-token'); setUser(buildUser({ id: 8 })); }}>Switch account</button><Reading /></>;
    }
    const { user } = renderWithProviders(<Harness />);
    await user.click(within(await suggestedCard()).getByRole('button', { name: `Not interested: ${PICK.title}` }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    await waitFor(() => expect(releaseFamily).toBeDefined());
    server.use(http.get('*/api/reading/recommendations/', () => HttpResponse.json({ results: [OTHER] })), http.get('*/api/reading-family-suggestions/', () => HttpResponse.json({ results: [] })));
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    expect(await screen.findByRole('article', { name: `Suggested book: ${OTHER.title}` })).toBeInTheDocument();
    await act(async () => { releaseFamily(); releaseFeedback(); });
    expect(screen.queryByText(FAMILY.message)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Undo' })).toBeNull();
    expect(screen.queryByText(`“${PICK.title}” hidden from your picks.`)).toBeNull();
  });
});
