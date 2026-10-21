import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import observed from '../../../contracts/api/fixtures/voyager-feedback-observed.json';
import empty from '../../../contracts/api/fixtures/voyager-feedback-empty.json';
import { server } from '../test/server';
import { getVoyagerFeedback } from './index';

describe('Voyager feedback through the shared React API client', () => {
  it.each([['observed', observed], ['empty', empty]])('preserves the actual %s family report without adding selectors or writes', async (_label, body) => {
    const calls = [];
    server.use(http.all('*/api/challenges/voyager-feedback/', ({ request }) => {
      calls.push({ method: request.method, authorization: request.headers.get('Authorization'), params: [...new URL(request.url).searchParams.keys()] });
      return HttpResponse.json(body);
    }));
    const controller = new AbortController();
    expect(await getVoyagerFeedback({ signal: controller.signal })).toEqual(body);
    expect(calls).toEqual([{ method: 'GET', authorization: 'Token test-session', params: ['_abby_session'] }]);
    expect(body.schema_version).toBe(1);
    expect(body.cohort.registered_within_days).toBe(180);
    if (body.status === 'observations_available') {
      expect(body.policy_groups.map((row) => row.policy)).toEqual(['saved_45_day', 'milestone_56_day', 'milestone_84_day', 'other_or_unknown']);
      const historical = body.policy_groups.find((row) => row.policy === 'milestone_56_day');
      expect(historical).toMatchObject({ label: '56 days · milestones', accepted_windows: 4, pending_windows: 2, mature_completed: 0, mature_expired: 1, mature_unknown: 1, mature_denominator: 1, completion_rate: 0 });
      const selected = body.policy_groups.find((row) => row.policy === 'milestone_84_day');
      expect(selected).toMatchObject({ label: '84 days · selected milestones', accepted_windows: 4, pending_windows: 2, mature_completed: 1, mature_expired: 1, mature_unknown: 0, mature_denominator: 2, completion_rate: 0.5 });
      expect(body.policy_groups.find((row) => row.policy === 'saved_45_day')).toMatchObject({ accepted_windows: 1, mature_completed: 1, mature_denominator: 1, completion_rate: 1 });
    } else expect(body.status).toBe('insufficient_evidence');
  });
});
