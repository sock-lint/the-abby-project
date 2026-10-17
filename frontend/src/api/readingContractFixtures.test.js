import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import book from '../../../contracts/api/fixtures/reading-book-created.json';
import finished from '../../../contracts/api/fixtures/reading-book-finished.json';
import books from '../../../contracts/api/fixtures/reading-books-list.json';
import session from '../../../contracts/api/fixtures/reading-session-created.json';
import corrected from '../../../contracts/api/fixtures/reading-session-corrected.json';
import sessions from '../../../contracts/api/fixtures/reading-sessions-list.json';
import summary from '../../../contracts/api/fixtures/reading-summary.json';
import invalid from '../../../contracts/api/fixtures/reading-session-invalid.json';
import notOwned from '../../../contracts/api/fixtures/reading-book-not-owned.json';
import progress from '../../../contracts/api/fixtures/reading-adventure-progress.json';
import rewarded from '../../../contracts/api/fixtures/reading-session-rewarded.json';
import rewardedSummary from '../../../contracts/api/fixtures/reading-summary-rewarded.json';
import discovery from '../../../contracts/api/fixtures/reading-discovery-picks.json';
import discoveryBook from '../../../contracts/api/fixtures/reading-discovery-book.json';
import feedback from '../../../contracts/api/fixtures/reading-discovery-feedback.json';
import familySuggestion from '../../../contracts/api/fixtures/reading-family-suggestion.json';
import familySuggestions from '../../../contracts/api/fixtures/reading-family-suggestions.json';
import savedSuggestions from '../../../contracts/api/fixtures/reading-family-suggestions-saved.json';
import dismissedSuggestion from '../../../contracts/api/fixtures/reading-family-suggestion-dismissed.json';
import { server } from '../test/server';
import {
  createReadingBook, createReadingSession, listReadingBooks, listReadingSessions,
  updateReadingBook, updateReadingSession, getReadingSummary,
  getReadingRecommendations, saveReadingDiscoveryFeedback,
  listReadingFamilySuggestions, createReadingFamilySuggestion, updateReadingFamilySuggestion,
} from './index';

describe('reading responses shared with Django', () => {
  it('preserves enriched discovery details and sends format filters without renderer negotiation', async () => {
    const reads = [];
    server.use(http.get('*/api/reading/recommendations/', ({ request }) => {
      const url = new URL(request.url);
      reads.push({ path: url.pathname, mood: url.searchParams.get('mood'), book_format: url.searchParams.get('book_format'), length: url.searchParams.get('length'), user_id: url.searchParams.get('user_id'), renderer: url.searchParams.get('format') });
      return HttpResponse.json(discovery);
    }));
    expect(await getReadingRecommendations({ mood: 'funny', book_format: 'ebook', length: 'short', user_id: 7 })).toEqual(discovery);
    expect(reads).toEqual([{ path: '/api/reading/recommendations/', mood: 'funny', book_format: 'ebook', length: 'short', user_id: '7', renderer: null }]);
    expect(discovery.results[0]).toMatchObject({ page_count: 180, moods: ['funny'], styles: ['illustrated'], formats: ['print', 'ebook'], series: null, reason_kind: 'filter' });
    expect(discoveryBook.catalog_entry.id).toBe(discovery.results[0].id);
    expect(discovery.has_more).toBe(false);
  });

  it('keeps feedback and attributed family suggestions separate from a child choosing to save', async () => {
    const writes = [];
    const capture = (result, status = 200) => async ({ request }) => {
      writes.push({ path: new URL(request.url).pathname, method: request.method, body: await request.json() });
      return HttpResponse.json(result, { status });
    };
    let saved = false;
    server.use(
      http.post('*/api/reading/discovery-feedback/', capture(feedback)),
      http.post('*/api/reading-family-suggestions/', capture(familySuggestion, 201)),
      http.get('*/api/reading-family-suggestions/', () => HttpResponse.json(saved ? savedSuggestions : familySuggestions)),
      http.post('*/api/reading-books/', async ({ request }) => {
        writes.push({ path: new URL(request.url).pathname, method: request.method, body: await request.json() });
        saved = true;
        return HttpResponse.json(discoveryBook, { status: 201 });
      }),
      http.patch('*/api/reading-family-suggestions/:id/', capture(dismissedSuggestion)),
    );
    const preference = { catalog_id: feedback.catalog_id, choice: feedback.choice };
    const invitation = { catalog_id: familySuggestion.catalog_id, user_id: 7, message: familySuggestion.message, client_request_id: familySuggestion.client_request_id };
    expect(await saveReadingDiscoveryFeedback(preference)).toEqual(feedback);
    expect(await createReadingFamilySuggestion(invitation)).toEqual(familySuggestion);
    expect(await listReadingFamilySuggestions()).toEqual(familySuggestions);
    expect(familySuggestions.results[0].on_shelf).toBe(false);
    expect(familySuggestions.results[0].suggested_by).toEqual({ id: 6, display_name: 'reading-fixture-parent' });
    expect(writes.some((write) => write.path === '/api/reading-books/')).toBe(false);
    const chosenBook = {
      title: discoveryBook.title, author: discoveryBook.author, interests: discoveryBook.interests,
      status: 'want_to_read', client_request_id: discoveryBook.client_request_id,
    };
    expect(await createReadingBook(chosenBook)).toEqual(discoveryBook);
    expect(await listReadingFamilySuggestions()).toEqual(savedSuggestions);
    expect(savedSuggestions.results[0].on_shelf).toBe(true);
    expect(await updateReadingFamilySuggestion(familySuggestion.id, { status: 'dismissed' })).toEqual(dismissedSuggestion);
    expect(writes).toEqual([
      { path: '/api/reading/discovery-feedback/', method: 'POST', body: preference },
      { path: '/api/reading-family-suggestions/', method: 'POST', body: invitation },
      { path: '/api/reading-books/', method: 'POST', body: chosenBook },
      { path: `/api/reading-family-suggestions/${familySuggestion.id}/`, method: 'PATCH', body: { status: 'dismissed' } },
    ]);
    expect(discoveryBook.status).toBe('want_to_read');
    expect(dismissedSuggestion.status).toBe('dismissed');
  });

  it('saves a book and reflection and reads the same scoped history and totals', async () => {
    const writes = [];
    const reads = [];
    const bookPayload = {
      title: book.title, author: book.author, status: book.status, interests: book.interests,
      client_request_id: book.client_request_id,
    };
    const sessionPayload = {
      book: session.book, occurred_on: session.occurred_on, duration_minutes: session.duration_minutes,
      pages_read: session.pages_read, section: session.section, format: session.format,
      reflection: session.reflection, reaction: session.reaction, client_request_id: session.client_request_id,
    };
    const capture = (body, status = 200) => async ({ request }) => {
      writes.push({ path: new URL(request.url).pathname, body: await request.json() });
      return HttpResponse.json(body, { status });
    };
    const read = (body) => ({ request }) => {
      expect(request.headers.get('Authorization')).toBe('Token test-session');
      const url = new URL(request.url);
      reads.push({ path: url.pathname, user: url.searchParams.get('user_id'), page: url.searchParams.get('page') });
      return HttpResponse.json(body);
    };
    server.use(
      http.post('*/api/reading-books/', capture(book, 201)),
      http.post('*/api/reading-sessions/', capture(session, 201)),
      http.get('*/api/reading-books/', read(books)),
      http.get('*/api/reading-sessions/', read(sessions)),
      http.get('*/api/reading/summary/', read(summary)),
    );
    expect(await createReadingBook(bookPayload)).toEqual(book);
    expect(await createReadingSession(sessionPayload)).toEqual(session);
    expect(writes).toEqual([
      { path: '/api/reading-books/', body: bookPayload },
      { path: '/api/reading-sessions/', body: sessionPayload },
    ]);
    expect(await listReadingBooks({ user_id: 7, page: 1 })).toEqual(books);
    expect(await listReadingSessions({ user_id: 7, page: 1 })).toEqual(sessions);
    expect(await getReadingSummary({ user_id: 7 })).toEqual(summary);
    expect(reads).toEqual([
      { path: '/api/reading-books/', user: '7', page: '1' },
      { path: '/api/reading-sessions/', user: '7', page: '1' },
      { path: '/api/reading/summary/', user: '7', page: null },
    ]);
    expect(summary).toMatchObject({ books_finished: 1, sessions_total: 1, total_minutes: 20, total_pages: 16 });
    expect(session.reading_reward).toBeNull();
    expect(summary.reading_adventure).toMatchObject({ earned: false, minutes_credited: 0, remaining_minutes: 10, base_xp: 15, base_coins: 5, xp_awarded: 0, coins_awarded: 0 });
  });

  it('corrects reading and marks a book finished without changing save identities', async () => {
    const writes = [];
    server.use(
      http.patch('*/api/reading-sessions/:id/', async ({ request, params }) => {
        writes.push({ id: params.id, body: await request.json() });
        return HttpResponse.json(corrected);
      }),
      http.patch('*/api/reading-books/:id/', async ({ request, params }) => {
        writes.push({ id: params.id, body: await request.json() });
        return HttpResponse.json(finished);
      }),
    );
    const correction = { pages_read: 16, reflection: corrected.reflection };
    expect(await updateReadingSession(session.id, correction)).toEqual(corrected);
    expect(await updateReadingBook(book.id, { status: 'finished' })).toEqual(finished);
    expect(writes).toEqual([
      { id: String(session.id), body: correction }, { id: String(book.id), body: { status: 'finished' } },
    ]);
    expect(corrected.client_request_id).toBe(session.client_request_id);
    expect(corrected.reading_reward).toBeNull();
    expect(finished.client_request_id).toBe(book.client_request_id);
  });

  it('retains backend field errors and inaccessible book errors', async () => {
    server.use(
      http.post('*/api/reading-sessions/', () => HttpResponse.json(invalid, { status: 400 })),
      http.patch('*/api/reading-books/:id/', () => HttpResponse.json(notOwned, { status: 404 })),
    );
    await expect(createReadingSession({ book: book.id, duration_minutes: -1 })).rejects.toMatchObject({ status: 400, response: invalid });
    await expect(updateReadingBook(book.id, { status: 'finished' })).rejects.toMatchObject({ status: 404, response: notOwned });
    expect(invalid.duration_minutes).toBeInstanceOf(Array);
  });

  it('preserves daily progress and actual boosted awards through session save, replay and later summary reads', async () => {
    const requests = [];
    let saved = false;
    const payload = {
      book: rewarded.book, occurred_on: rewarded.occurred_on, duration_minutes: rewarded.duration_minutes,
      pages_read: rewarded.pages_read, section: rewarded.section, format: rewarded.format,
      reflection: rewarded.reflection, reaction: rewarded.reaction, client_request_id: rewarded.client_request_id,
    };
    server.use(
      http.get('*/api/reading/summary/', ({ request }) => {
        const url = new URL(request.url);
        requests.push({ method: request.method, path: url.pathname, user_id: url.searchParams.get('user_id') });
        return HttpResponse.json(saved ? rewardedSummary : progress);
      }),
      http.post('*/api/reading-sessions/', async ({ request }) => {
        requests.push({ method: request.method, path: new URL(request.url).pathname, body: await request.json() });
        saved = true;
        return HttpResponse.json(rewarded, { status: 201 });
      }),
    );
    const before = await getReadingSummary({ user_id: 7 });
    expect(before).toEqual(progress);
    expect(before.reading_adventure).toEqual({ day: progress.today, target_minutes: 10, minutes_credited: 4, remaining_minutes: 6, earned: false, base_xp: 15, base_coins: 5, xp_awarded: 0, coins_awarded: 0, skill_name: 'Reading Comprehension' });
    const savedSession = await createReadingSession(payload);
    const replay = await createReadingSession(payload);
    expect(savedSession).toEqual(rewarded);
    expect(replay.reading_reward).toEqual(savedSession.reading_reward);
    expect(savedSession.reading_reward).toEqual({ day: progress.today, xp_awarded: 30, coins_awarded: 10 });
    const after = await getReadingSummary({ user_id: 7 });
    expect(after).toEqual(rewardedSummary);
    expect(after.reading_adventure).toEqual({ ...before.reading_adventure, minutes_credited: 10, remaining_minutes: 0, earned: true, xp_awarded: 30, coins_awarded: 10 });
    expect(requests).toEqual([
      { method: 'GET', path: '/api/reading/summary/', user_id: '7' },
      { method: 'POST', path: '/api/reading-sessions/', body: payload },
      { method: 'POST', path: '/api/reading-sessions/', body: payload },
      { method: 'GET', path: '/api/reading/summary/', user_id: '7' },
    ]);
  });
});
