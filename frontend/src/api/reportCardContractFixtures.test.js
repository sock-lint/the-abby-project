import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import createdCard from '../../../contracts/api/fixtures/report-card-created.json';
import correctedCard from '../../../contracts/api/fixtures/report-card-corrected.json';
import reportCards from '../../../contracts/api/fixtures/report-cards-list.json';
import invalidCard from '../../../contracts/api/fixtures/report-card-invalid.json';
import { server } from '../test/server';
import { getGrades, updateGradeEntry, writeGrade } from './index';

describe('report card responses through the shared React API client', () => {
  it('saves a complete quarter and reads both quarter and semester history with confirmed rewards', async () => {
    const requests = [];
    const payload = {
      report_card: createdCard.metadata.report_card,
      reflection: createdCard.summary,
      occurred_on: createdCard.occurred_on,
      is_private: createdCard.is_private,
      client_entry_id: createdCard.client_entry_id,
    };
    server.use(
      http.post('*/api/chronicle/grades/', async ({ request }) => {
        requests.push({ url: request.url, body: await request.json() });
        return HttpResponse.json(createdCard, { status: 201 });
      }),
      http.get('*/api/chronicle/grades/', ({ request }) => {
        expect(request.headers.get('Authorization')).toBe('Token test-session');
        return HttpResponse.json(reportCards);
      }),
    );
    const saved = await writeGrade(payload);
    expect(saved).toEqual(createdCard);
    expect(saved.metadata.report_card.subjects).toEqual([
      { subject: 'Math', grade_format: 'percentage', score: '92.5' },
      { subject: 'Science', grade_format: 'points', score: '11.25', possible: '10' },
      { subject: 'English', grade_format: 'letter', letter: 'A-' },
    ]);
    expect(saved.reward_receipt).toEqual(createdCard.reward_receipt);
    expect(requests).toHaveLength(1);
    expect(new URL(requests[0].url).pathname).toBe('/api/chronicle/grades/');
    expect(requests[0].body).toEqual(payload);
    const history = await getGrades();
    expect(history).toEqual(reportCards);
    expect(history.results.map((entry) => entry.metadata.report_card.period_type)).toEqual(['quarter', 'semester']);
    expect(history.results[1].reward_receipt).toMatchObject({ status: 'daily_limit', xp_awarded: 0 });
  });

  it('patches the selected report card and preserves its original receipt and subject marking formats', async () => {
    const requests = [];
    const payload = {
      report_card: correctedCard.metadata.report_card,
      reflection: correctedCard.summary,
      is_private: correctedCard.is_private,
    };
    server.use(http.patch('*/api/chronicle/:entryId/grade/', async ({ request, params }) => {
      requests.push({ id: params.entryId, body: await request.json() });
      return HttpResponse.json(correctedCard);
    }));
    const saved = await updateGradeEntry(createdCard.id, payload);
    expect(saved).toEqual(correctedCard);
    expect(requests).toEqual([{ id: String(createdCard.id), body: payload }]);
    expect(saved.reward_receipt).toEqual(createdCard.reward_receipt);
    expect(saved.client_entry_id).toBe(createdCard.client_entry_id);
    expect(saved.metadata.report_card.subjects[0].score).toBe('95');
    expect(saved.metadata.report_card.subjects[1]).toEqual(createdCard.metadata.report_card.subjects[1]);
    expect(saved.metadata.report_card.subjects[2]).toEqual(createdCard.metadata.report_card.subjects[2]);
  });

  it('retains indexed subject validation errors and makes only one rejected request', async () => {
    const requests = [];
    const invalid = {
      report_card: {
        ...createdCard.metadata.report_card,
        subjects: createdCard.metadata.report_card.subjects.map((subject, index) => (
          index === 0 ? { ...subject, xp_awarded: 1000 } : subject
        )),
      },
      client_entry_id: createdCard.client_entry_id,
    };
    server.use(http.post('*/api/chronicle/grades/', async ({ request }) => {
      requests.push(await request.json());
      return HttpResponse.json(invalidCard, { status: 400 });
    }));
    await expect(writeGrade(invalid)).rejects.toMatchObject({ status: 400, response: invalidCard });
    expect(requests).toEqual([invalid]);
    expect(invalidCard.report_card.subjects[0]).toHaveProperty('xp_awarded');
  });
});
