import { http, HttpResponse } from 'msw';
import family from '../../../contracts/api/fixtures/usage-family-observed.json';
import deployment from '../../../contracts/api/fixtures/usage-deployment-observed.json';
import empty from '../../../contracts/api/fixtures/usage-family-empty.json';
import childChores from '../../../contracts/api/fixtures/usage-family-child-chores.json';
import { server } from '../test/server';
import { getUsageDashboard, recordUsageVisit } from './index';

describe('usage responses shared with Django', () => {
  it.each([['family', family], ['deployment', deployment], ['family', childChores], ['family', empty]])('preserves the real %s aggregate report and bounded filter contract', async (scope, fixture) => {
    let requested;
    server.use(http.get('*/api/admin/usage/', ({ request }) => {
      const url = new URL(request.url);
      requested = { method: request.method, path: url.pathname, scope: url.searchParams.get('scope'), days: url.searchParams.get('days'), role: url.searchParams.get('role'), feature: url.searchParams.get('feature') };
      return HttpResponse.json(fixture);
    }));
    const response = await getUsageDashboard({ scope, ...fixture.filters });
    expect(response).toEqual(fixture);
    expect(requested).toEqual({ method: 'GET', path: '/api/admin/usage/', scope, days: String(fixture.filters.days), role: fixture.filters.role, feature: fixture.filters.feature });
    expect(response.retention.week_4.history_complete).toBe(fixture.retention.week_4.history_complete);
    expect(response.retention.week_4.rate).toBe(fixture.retention.week_4.rate);
    expect(response.collection.previous_history_complete).toBe(fixture.collection.previous_history_complete);
    expect(JSON.stringify(response)).not.toContain('Synthetic private');
  });

  it('sends only the empty visit POST accepted by the producer and accepts its 204 receipt', async () => {
    let received;
    server.use(http.post('*/api/usage/visit/', async ({ request }) => {
      received = { body: await request.json(), path: new URL(request.url).pathname, method: request.method };
      return new HttpResponse(null, { status: 204 });
    }));
    expect(await recordUsageVisit()).toBeNull();
    expect(received).toEqual({ method: 'POST', path: '/api/usage/visit/', body: {} });
  });
});
