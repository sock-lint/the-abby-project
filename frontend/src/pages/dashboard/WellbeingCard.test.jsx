import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import WellbeingCard from './WellbeingCard.jsx';
import JournalReader from '../chronicle/JournalReader.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';
import { buildUser } from '../../test/factories.js';
import { journalDraftKey } from '../yearbook/journalDraft';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const TODAY = new Date().toLocaleDateString('en-CA');
const AFFIRMATION = { affirmation: { text: 'You are enough today, exactly as you are.' }, gratitude_lines: [] };
const receipt = { status: 'awarded', xp_awarded: 19, coins_awarded: 2, coin_status: 'awarded' };

function renderCard(handlers = []) {
  server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
    http.get('*/api/wellbeing/today/', () => HttpResponse.json(AFFIRMATION)), ...handlers);
  return render(<MemoryRouter><AuthProvider><Routes>
    <Route path="/" element={<WellbeingCard />} />
    <Route path="/chronicle" element={<JournalReader />} />
  </Routes></AuthProvider></MemoryRouter>);
}

describe('Today journal entry point', () => {
  it('checks again before capture when another entry point saved since Today loaded', async () => {
    let saved = null;
    renderCard([http.get('*/api/chronicle/journal/today/', () => saved ? HttpResponse.json(saved) : new HttpResponse(null, { status: 204 }))]);
    const user = userEvent.setup();
    const write = await screen.findByRole('button', { name: 'Write today’s entry' });
    saved = { id: 42, title: 'Saved elsewhere', summary: 'Keep these words', occurred_on: TODAY, is_private: false };
    await user.click(write);
    const dialog = await screen.findByRole('dialog', { name: 'Edit your journal entry' });
    expect(within(dialog).getByLabelText(/mind/i)).toHaveValue('Keep these words');
    expect(within(dialog).getByRole('checkbox', { name: /share with parents/i })).toBeChecked();
  });

  it('keeps capture disabled until the first today lookup finishes', async () => {
    let finish;
    const ready = new Promise((resolve) => { finish = resolve; });
    renderCard([http.get('*/api/chronicle/journal/today/', async () => { await ready; return new HttpResponse(null, { status: 204 }); })]);
    expect(await screen.findByRole('button', { name: 'Checking today’s entry…' })).toBeDisabled();
    expect(screen.queryByRole('dialog')).toBeNull();
    finish();
    expect(await screen.findByRole('button', { name: 'Write today’s entry' })).toBeEnabled();
  });

  it('saves through the shared private journal flow and finds the same words in Memories', async () => {
    let saved;
    const post = spyHandler('post', /\/api\/chronicle\/journal\/$/, ({ body }) => {
      saved = { ...body, id: 42, user: 1, kind: 'journal', occurred_on: TODAY, title: 'A difficult afternoon', reward_receipt: receipt };
      return saved;
    });
    const oldPost = spyHandler('post', /\/api\/wellbeing\/today\/gratitude\/$/, {});
    renderCard([
      http.get('*/api/chronicle/journal/today/', () => saved ? HttpResponse.json(saved) : new HttpResponse(null, { status: 204 })),
      http.get('*/api/chronicle/summary/', () => HttpResponse.json({ chapters: [{ chapter_year: 2026, label: 'This year', is_current: true, entries: saved ? [saved] : [] }] })),
      post.handler, oldPost.handler,
    ]);
    const user = userEvent.setup();
    expect(await screen.findByText(AFFIRMATION.affirmation.text)).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Write today’s entry' }));
    const dialog = await screen.findByRole('dialog', { name: 'Write in your journal' });
    await user.type(within(dialog).getByLabelText(/mind/i), 'A difficult afternoon. I asked for help.');
    expect(within(dialog).getByRole('checkbox', { name: /share with parents/i })).not.toBeChecked();
    await user.click(within(dialog).getByRole('button', { name: 'Save entry' }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    expect(post.calls[0].body).toEqual({ title: '', summary: 'A difficult afternoon. I asked for help.', is_private: true, client_entry_id: expect.stringMatching(/^[0-9a-f-]{36}$/) });
    expect(post.calls[0].url).toMatch(/\/api\/chronicle\/journal\/$/);
    expect(oldPost.calls).toHaveLength(0);
    expect(await screen.findByText('+19 XP earned')).toBeInTheDocument();
    expect(screen.getByText('+2 Coins earned')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(await screen.findByText('A difficult afternoon. I asked for help.')).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Memories → Journal' }));
    expect(await screen.findByRole('heading', { name: 'A difficult afternoon' })).toBeInTheDocument();
    expect(screen.getByText('A difficult afternoon. I asked for help.')).toBeInTheDocument();
  });

  it('reopens today’s shared entry and PATCHes it without another reward or sharing change', async () => {
    const saved = { id: 42, title: 'My day', summary: 'Warm bread', kind: 'journal', is_private: false, occurred_on: TODAY, reward_receipt: receipt };
    const patch = spyHandler('patch', /\/api\/chronicle\/42\/journal\/$/, ({ body }) => ({ ...saved, ...body }));
    const post = spyHandler('post', /\/api\/chronicle\/journal\/$/, {});
    renderCard([http.get('*/api/chronicle/journal/today/', () => HttpResponse.json(saved)), patch.handler, post.handler]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Edit today’s entry' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit your journal entry' });
    expect(within(dialog).getByRole('checkbox', { name: /share with parents/i })).toBeChecked();
    await user.type(within(dialog).getByLabelText(/mind/i), ' and a walk together');
    await user.click(within(dialog).getByRole('button', { name: 'Update entry' }));
    await waitFor(() => expect(patch.calls).toHaveLength(1));
    expect(patch.calls[0].body).toEqual({ title: 'My day', summary: 'Warm bread and a walk together', is_private: false });
    expect(patch.calls[0].url).toMatch(/\/api\/chronicle\/42\/journal\/$/);
    expect(post.calls).toHaveLength(0);
    await screen.findByRole('dialog', { name: 'Entry updated' });
    expect(screen.queryByText(/XP earned|Coins earned/)).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Done' }));
    expect(await screen.findByText('Warm bread and a walk together')).toBeInTheDocument();
  });

  it('keeps an unconfirmed save draft when moving from Today into Journal', async () => {
    const post = spyHandler('post', /\/api\/chronicle\/journal\/$/, HttpResponse.json({ detail: 'Temporarily unavailable' }, { status: 503 }));
    renderCard([post.handler, http.get('*/api/chronicle/summary/', () => HttpResponse.json({ chapters: [] }))]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Write today’s entry' }));
    await user.type(screen.getByLabelText(/mind/i), 'Keep my private words');
    await user.click(screen.getByRole('button', { name: 'Save entry' }));
    await screen.findByText(/we could not confirm the save/i);
    const draft = JSON.parse(localStorage.getItem(journalDraftKey(1)));
    expect(draft.pending.payload).toEqual(post.calls[0].body);
    await user.click(screen.getByRole('button', { name: /keep draft & close/i }));
    await user.click(screen.getByRole('link', { name: 'Memories → Journal' }));
    await user.click(await screen.findByRole('button', { name: 'Write today’s entry' }));
    expect(screen.getByLabelText(/mind/i)).toHaveValue('Keep my private words');
    expect(screen.getByLabelText(/mind/i)).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Check save' })).toBeInTheDocument();
  });

  it('holds capture during a failed today lookup and retries without mistaking failure for no entry', async () => {
    let failed = true;
    renderCard([http.get('*/api/chronicle/journal/today/', () => failed
      ? HttpResponse.json({ detail: 'Journal temporarily unavailable' }, { status: 503 })
      : HttpResponse.json({ id: 42, summary: 'Already saved', title: 'My day', is_private: true, occurred_on: TODAY }))]);
    const user = userEvent.setup();
    expect(await screen.findByText('Journal temporarily unavailable')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Write today’s entry' })).toBeNull();
    failed = false;
    await user.click(screen.getByRole('button', { name: /try again/i }));
    await user.click(await screen.findByRole('button', { name: 'Edit today’s entry' }));
    expect(screen.getByLabelText(/mind/i)).toHaveValue('Already saved');
  });

  it('keeps journal capture available if the optional affirmation cannot load', async () => {
    renderCard([http.get('*/api/wellbeing/today/', () => HttpResponse.json({}, { status: 503 }))]);
    const user = userEvent.setup();
    await user.click(await screen.findByRole('button', { name: 'Write today’s entry' }));
    expect(await screen.findByRole('dialog', { name: 'Write in your journal' })).toBeInTheDocument();
  });
});
