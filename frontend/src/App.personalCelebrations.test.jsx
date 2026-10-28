import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import * as Sentry from '@sentry/react';
import App from './App';
import { AuthProvider, DEFERRED_RECOVERY_DELAY_MS } from './hooks/useApi';
import { GATEWAY_RETRY_DELAY_MS } from './api/client';
import { server } from './test/server';
import { buildParent, buildUser } from './test/factories';

vi.mock('framer-motion', async importOriginal => ({ ...await importOriginal(), AnimatePresence: ({ children }) => children }));
const parent = buildParent({ id: 90, family: { id: 1 } });
const perfectDay = { id: 31, notification_type: 'perfect_day', title: 'Perfect day', message: '' };
function renderApp() { return render(<AuthProvider><App /></AuthProvider>); }
function personalPreference() { sessionStorage.setItem('abby:spaces:1:90', JSON.stringify({ space: 'personal' })); }
beforeEach(() => {
  sessionStorage.clear();
  window.history.replaceState({}, '', '/');
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(parent)));
});
afterEach(() => { window.history.replaceState({}, '', '/'); vi.useRealTimers(); });

describe('Personal celebrations within the active workspace', () => {
  it('leaves Family catch-up unread, then shows and acknowledges it in My space', async () => {
    const reads = [];
    const marks = [];
    let marked = false;
    server.use(
      http.get('*/api/notifications/pending-celebration/', ({ request }) => { reads.push(request.headers.get('x-abby-space')); return marked ? new HttpResponse(null, { status: 204 }) : HttpResponse.json(perfectDay); }),
      http.post('*/api/notifications/31/mark_read/', ({ request }) => { marked = true; marks.push(request.headers.get('x-abby-space')); return HttpResponse.json({ id: 31, is_read: true }); }),
    );
    const user = userEvent.setup();
    renderApp();
    await screen.findByRole('heading', { name: 'Today', level: 1 });
    expect(screen.getByRole('button', { name: /^Family/ })).toHaveAttribute('aria-pressed', 'true');
    expect(reads).toEqual([]);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'My space' }));
    expect(await screen.findByRole('alertdialog', { name: 'Perfect day' })).toBeInTheDocument();
    expect(reads).toEqual(['personal']);
    await user.click(screen.getByRole('button', { name: /Turn the page/ }));
    await waitFor(() => expect(marks).toEqual(['personal']));
    await user.click(screen.getByRole('button', { name: /^Family/ }));
    await user.click(screen.getByRole('button', { name: 'My space' }));
    await waitFor(() => expect(reads).toHaveLength(2));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('keeps child celebration reads and acknowledgments on their existing credential scope', async () => {
    const reads = [];
    const marks = [];
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/notifications/pending-celebration/', ({ request }) => { reads.push(request.headers.get('x-abby-space')); return HttpResponse.json(perfectDay); }),
      http.post('*/api/notifications/31/mark_read/', ({ request }) => { marks.push(request.headers.get('x-abby-space')); return HttpResponse.json({}); }));
    const user = userEvent.setup();
    renderApp();
    await screen.findByRole('alertdialog', { name: 'Perfect day' });
    await user.click(screen.getByRole('button', { name: /Turn the page/ }));
    await waitFor(() => expect(marks).toEqual([null]));
    expect(reads).toEqual([null]);
    expect(screen.queryByRole('button', { name: 'My space' })).not.toBeInTheDocument();
  });

  it('preserves birthday priority and personal acknowledgment before showing an own streak', async () => {
    personalPreference();
    const birthdayMarks = [];
    server.use(http.get('*/api/chronicle/pending-celebration/', () => HttpResponse.json({ id: 9, kind: 'birthday', title: 'Turned 45', metadata: { gift_coins: 10 } })),
      http.post('*/api/chronicle/9/mark-viewed/', ({ request }) => { birthdayMarks.push(request.headers.get('x-abby-space')); return HttpResponse.json({}); }),
      http.get('*/api/notifications/pending-celebration/', () => HttpResponse.json({ id: 32, notification_type: 'streak_milestone', title: '30-day streak!', message: '' })));
    const user = userEvent.setup();
    renderApp();
    expect(await screen.findByRole('alertdialog', { name: 'Happy birthday' })).toBeInTheDocument();
    expect(screen.getAllByRole('alertdialog')).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: /Turn the page/ }));
    await waitFor(() => expect(birthdayMarks).toEqual(['personal']));
    expect(await screen.findByRole('alertdialog', { name: '30-day streak!' })).toBeInTheDocument();
  });

  it('retains a dirty Family form without fetching or consuming personal celebrations', async () => {
    window.history.replaceState({}, '', '/quests/ventures/new');
    const reads = [];
    server.use(http.get('*/api/notifications/pending-celebration/', ({ request }) => { reads.push(request.headers.get('x-abby-space')); return HttpResponse.json(perfectDay); }));
    const user = userEvent.setup();
    renderApp();
    const title = await screen.findByLabelText('Title');
    await user.type(title, 'Unfinished family project');
    expect(screen.getByRole('button', { name: 'My space' })).toBeDisabled();
    expect(reads).toEqual([]);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await user.clear(title);
    await waitFor(() => expect(screen.getByRole('button', { name: 'My space' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'My space' }));
    expect(await screen.findByRole('alertdialog', { name: 'Perfect day' })).toBeInTheDocument();
    expect(reads).toEqual(['personal']);
  });

  it('aborts an in-flight personal read on a space switch and discards its late response', async () => {
    personalPreference();
    let readSignal;
    let resolveRead;
    server.use(http.get('*/api/notifications/pending-celebration/', ({ request }) => {
      readSignal = request.signal;
      return new Promise(resolve => { resolveRead = resolve; });
    }));
    const user = userEvent.setup();
    renderApp();
    await waitFor(() => expect(resolveRead).toBeTypeOf('function'));
    await user.click(screen.getByRole('button', { name: /^Family/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /^Family/ })).toHaveAttribute('aria-pressed', 'true'));
    expect(readSignal.aborted).toBe(true);
    await act(async () => resolveRead(HttpResponse.json(perfectDay)));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('cancels the #354 deferred retry when leaving My space', async () => {
    personalPreference();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const reads = [];
    server.use(http.get('*/api/notifications/pending-celebration/', ({ request }) => {
      reads.push(request.headers.get('x-abby-space'));
      return new HttpResponse('<!doctype html><title>starting</title>', { status: 200, headers: { 'content-type': 'text/html' } });
    }));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderApp();
    await act(() => vi.advanceTimersByTimeAsync(GATEWAY_RETRY_DELAY_MS));
    await waitFor(() => expect(reads).toHaveLength(2));
    await user.click(screen.getByRole('button', { name: /^Family/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /^Family/ })).toHaveAttribute('aria-pressed', 'true'));
    await act(() => vi.advanceTimersByTimeAsync(DEFERRED_RECOVERY_DELAY_MS * 2));
    expect(reads).toEqual(['personal', 'personal']);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(Sentry.captureException).not.toHaveBeenCalled();
  });
});
