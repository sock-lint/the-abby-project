import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import createdJournal from '../../../contracts/api/fixtures/journal-created.json';
import replayedJournal from '../../../contracts/api/fixtures/journal-replayed.json';
import todayJournal from '../../../contracts/api/fixtures/journal-today.json';
import editedJournal from '../../../contracts/api/fixtures/journal-edited.json';
import alreadyReceivedJournal from '../../../contracts/api/fixtures/journal-coins-already-received.json';
import renamedTaxonomyJournal from '../../../contracts/api/fixtures/journal-renamed-taxonomy.json';
import history from '../../../contracts/api/fixtures/journal-summary-legacy.json';
import parentPrivateHistory from '../../../contracts/api/fixtures/journal-summary-parent-private.json';
import { server } from '../test/server';
import { getChronicleSummary, getTodayJournal, updateJournalEntry, writeJournal } from './index';

const submission = {
  title: createdJournal.title,
  summary: createdJournal.summary,
  is_private: createdJournal.is_private,
  client_entry_id: createdJournal.client_entry_id,
};

describe('unified journal responses through the shared React API client', () => {
  it('retains measured journal XP and exact skill IDs after supported taxonomy renames', async () => {
    server.use(http.post('*/api/chronicle/journal/', () => (
      HttpResponse.json(renamedTaxonomyJournal, { status: 201 })
    )));
    const saved = await writeJournal(submission);
    expect(saved).toEqual(renamedTaxonomyJournal);
    expect(saved.reward_receipt).toMatchObject({
      status: 'awarded', xp_awarded: 15, coins_awarded: 2, coin_status: 'awarded',
      skills: [
        { skill_id: 32, name: 'Story Craft', xp: 10 },
        { skill_id: 33, name: 'Word Power', xp: 5 },
      ],
    });
    expect(saved.metadata.reward_receipt.skills).toEqual(saved.reward_receipt.skills);
  });

  it('saves, replays and reads the same private journal with measured daily rewards', async () => {
    const requests = [];
    server.use(
      http.post('*/api/chronicle/journal/', async ({ request }) => {
        expect(request.headers.get('Authorization')).toBe('Token test-session');
        requests.push(await request.json());
        return requests.length === 1
          ? HttpResponse.json(createdJournal, { status: 201 })
          : HttpResponse.json(replayedJournal);
      }),
      http.get('*/api/chronicle/journal/today/', () => HttpResponse.json(todayJournal)),
    );
    const saved = await writeJournal(submission);
    expect(saved).toEqual(createdJournal);
    expect(saved.reward_receipt).toMatchObject({
      status: 'awarded', xp_awarded: 15, coins_awarded: 2, coin_status: 'awarded',
    });
    expect(saved.is_private).toBe(true);
    expect(await writeJournal(submission)).toEqual(saved);
    expect(await getTodayJournal()).toEqual(saved);
    expect(requests).toEqual([submission, submission]);
  });

  it('updates the saved journal and retains its original reward receipt', async () => {
    const requests = [];
    const payload = { summary: editedJournal.summary };
    server.use(http.patch('*/api/chronicle/:entryId/journal/', async ({ request, params }) => {
      requests.push({ id: params.entryId, body: await request.json() });
      return HttpResponse.json(editedJournal);
    }));
    const saved = await updateJournalEntry(createdJournal.id, payload);
    expect(saved).toEqual(editedJournal);
    expect(saved.reward_receipt).toEqual(createdJournal.reward_receipt);
    expect(saved.client_entry_id).toBe(createdJournal.client_entry_id);
    expect(requests).toEqual([{ id: String(createdJournal.id), body: payload }]);
  });

  it('keeps a previously paid daily note and the ordinary journal in one private history', async () => {
    server.use(http.get('*/api/chronicle/summary/', ({ request }) => {
      expect(request.headers.get('Authorization')).toBe('Token test-session');
      return HttpResponse.json(history);
    }));
    const saved = await getChronicleSummary();
    expect(saved).toEqual(history);
    const entries = saved.chapters.flatMap((chapter) => chapter.entries);
    expect(entries.map((entry) => entry.kind)).toEqual(['journal', 'daily_note']);
    expect(entries.every((entry) => entry.is_private)).toBe(true);
    expect(entries[1].summary).toBe('A small note from yesterday.\n\nA friend listened.');
    expect(entries[1].reward_receipt).toMatchObject({
      status: 'unavailable', xp_awarded: 0, coins_awarded: 0, coin_status: 'unavailable',
    });
  });

  it('retains the separate already-received coin status without claiming another payout', async () => {
    server.use(http.post('*/api/chronicle/journal/', () => (
      HttpResponse.json(alreadyReceivedJournal, { status: 201 })
    )));
    const saved = await writeJournal(submission);
    expect(saved.reward_receipt).toMatchObject({
      status: 'awarded', xp_awarded: 15, coins_awarded: 0, coin_status: 'already_received',
    });
  });

  it('keeps private journal and legacy note contents out of a parent history response', async () => {
    server.use(http.get('*/api/chronicle/summary/', ({ request }) => {
      expect(new URL(request.url).searchParams.get('user_id')).toBe(String(createdJournal.user));
      return HttpResponse.json(parentPrivateHistory);
    }));
    expect(await getChronicleSummary(createdJournal.user)).toEqual({
      chapters: [], current_chapter_year: 2026,
    });
  });
});
