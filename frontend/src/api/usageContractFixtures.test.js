import { http, HttpResponse } from 'msw';
import family from '../../../contracts/api/fixtures/usage-family-observed.json';
import deployment from '../../../contracts/api/fixtures/usage-deployment-observed.json';
import empty from '../../../contracts/api/fixtures/usage-family-empty.json';
import childChores from '../../../contracts/api/fixtures/usage-family-child-chores.json';
import childLogin from '../../../contracts/api/fixtures/auth-login-child.json';
import childMe from '../../../contracts/api/fixtures/auth-me-child.json';
import parentLogin from '../../../contracts/api/fixtures/auth-login-ordinary-parent.json';
import parentMe from '../../../contracts/api/fixtures/auth-me-ordinary-parent.json';
import staffLogin from '../../../contracts/api/fixtures/auth-login-staff-parent.json';
import staffMe from '../../../contracts/api/fixtures/auth-me-staff-parent.json';
import liveParentLogin from '../../../contracts/api/fixtures/auth-login-live-parent.json';
import liveParentMe from '../../../contracts/api/fixtures/auth-me-live-parent.json';
import liveChildLogin from '../../../contracts/api/fixtures/auth-login-live-child.json';
import liveChildMe from '../../../contracts/api/fixtures/auth-me-live-child.json';
import { server } from '../test/server';
import { getMe, getUsageDashboard, login, recordUsageVisit } from './index';

describe('usage responses shared with Django', () => {
  it.each([
    ['ordinary child', childLogin, childMe, true],
    ['ordinary parent', parentLogin, parentMe, true],
    ['staff parent', staffLogin, staffMe, true],
    ['observer parent', liveParentLogin, liveParentMe, false],
    ['observer child', liveChildLogin, liveChildMe, false],
  ])('preserves the server collection policy through %s login and verified identity', async (_label, loginFixture, meFixture, enabled) => {
    server.use(
      http.post('*/api/auth/', () => HttpResponse.json(loginFixture)),
      http.get('*/api/auth/me/', () => HttpResponse.json(meFixture)),
    );
    const authenticated = await login(loginFixture.username, 'synthetic-password');
    expect(authenticated).toEqual(loginFixture);
    expect(authenticated.usage_collection_enabled).toBe(enabled);
    const verified = await getMe();
    expect(verified).toEqual(meFixture);
    expect(verified.usage_collection_enabled).toBe(enabled);
  });

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
