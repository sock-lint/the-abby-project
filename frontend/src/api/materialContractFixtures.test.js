import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import unready from '../../../contracts/api/fixtures/material-unready.json';
import listing from '../../../contracts/api/fixtures/material-list.json';
import ready from '../../../contracts/api/fixtures/material-ready.json';
import purchasedZero from '../../../contracts/api/fixtures/material-purchased-zero.json';
import purchased from '../../../contracts/api/fixtures/material-purchased.json';
import notOwned from '../../../contracts/api/fixtures/material-not-owned.json';
import { server } from '../test/server';
import { getMaterials, markMaterialNotReady, markMaterialReady, markPurchased } from './index';

describe('material readiness through the shared React API client', () => {
  it('reads the paginated material list and preserves server readiness separately from purchases', async () => {
    server.use(http.get('*/api/projects/401/materials/', ({ request }) => {
      expect(request.headers.get('Authorization')).toBe('Token test-session');
      return HttpResponse.json(listing);
    }));
    const materials = await getMaterials(401);
    expect(materials).toEqual(listing);
    expect(materials.results).toEqual([unready]);
    expect(materials.results[0]).toMatchObject({ is_ready: false, is_purchased: false, actual_cost: null });
  });

  it('marks a material ready and corrects it with empty requests without claiming a purchase', async () => {
    const requests = [];
    server.use(
      http.post('*/api/projects/401/materials/701/mark-ready/', async ({ request }) => {
        requests.push({ path: new URL(request.url).pathname, body: await request.json() });
        expect(request.headers.get('Authorization')).toBe('Token test-session');
        return HttpResponse.json(ready);
      }),
      http.post('*/api/projects/401/materials/701/mark-not-ready/', async ({ request }) => {
        requests.push({ path: new URL(request.url).pathname, body: await request.json() });
        expect(request.headers.get('Authorization')).toBe('Token test-session');
        return HttpResponse.json(unready);
      }),
    );
    expect(await markMaterialReady(401, 701)).toEqual(ready);
    expect(await markMaterialNotReady(401, 701)).toEqual(unready);
    expect(await markMaterialNotReady(401, 701)).toEqual(unready);
    expect(requests).toEqual([
      { path: '/api/projects/401/materials/701/mark-ready/', body: {} },
      { path: '/api/projects/401/materials/701/mark-not-ready/', body: {} },
      { path: '/api/projects/401/materials/701/mark-not-ready/', body: {} },
    ]);
    expect(ready).toMatchObject({ is_ready: true, is_purchased: false, actual_cost: null });
    expect(unready).toMatchObject({ is_ready: false, is_purchased: false, actual_cost: null });
  });

  it.each([
    ['0.00', purchasedZero],
    ['2.75', purchased],
  ])('records an explicit %s actual purchase cost without replacing it with the estimate', async (cost, body) => {
    const requests = [];
    server.use(http.post('*/api/projects/401/materials/701/mark-purchased/', async ({ request }) => {
      requests.push(await request.json());
      return HttpResponse.json(body);
    }));
    expect(await markPurchased(401, 701, cost)).toEqual(body);
    expect(requests).toEqual([{ actual_cost: cost }]);
    expect(body.actual_cost).toBe(cost);
    expect(body.estimated_cost).toBe('3.00');
    expect(body.is_ready).toBe(true);
  });

  it('retains confirmed purchase fields when clearing a separate on-hand mark', async () => {
    const requests = [];
    server.use(http.post('*/api/projects/401/materials/701/mark-not-ready/', async ({ request }) => {
      requests.push(await request.json());
      return HttpResponse.json(purchased);
    }));
    expect(await markMaterialNotReady(401, 701)).toEqual(purchased);
    expect(requests).toEqual([{}]);
    expect(purchased).toMatchObject({ is_ready: true, is_purchased: true, actual_cost: '2.75' });
  });

  it.each([
    ['mark-ready', markMaterialReady],
    ['mark-not-ready', markMaterialNotReady],
  ])('propagates a family-scoped rejection without replaying the %s write', async (action, changeReadiness) => {
    const requests = [];
    server.use(http.post(`*/api/projects/401/materials/701/${action}/`, async ({ request }) => {
      requests.push(await request.json());
      return HttpResponse.json(notOwned, { status: 404 });
    }));
    await expect(changeReadiness(401, 701)).rejects.toMatchObject({ status: 404, response: notOwned });
    expect(requests).toEqual([{}]);
  });
});
