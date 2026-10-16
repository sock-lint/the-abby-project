import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import budget from '../../../contracts/api/fixtures/printing-budget-configured.json';
import quoted from '../../../contracts/api/fixtures/printing-request-quoted.json';
import requestsQuoted from '../../../contracts/api/fixtures/printing-requests-quoted.json';
import paid from '../../../contracts/api/fixtures/printing-exchange-paid.json';
import refunded from '../../../contracts/api/fixtures/printing-cancel-refunded.json';
import invalidExchange from '../../../contracts/api/fixtures/printing-exchange-invalid.json';
import notOwned from '../../../contracts/api/fixtures/printing-request-not-owned.json';
import { server } from '../test/server';
import {
  approvePrintRequest, cancelPrintRequest, exchangePrintRequest,
  listPrintRequests, updatePrintBudget,
} from './index';

describe('printing Coin responses through the shared React API client', () => {
  it('saves a parent rate and returns the server quote without changing its Coin or decimal types', async () => {
    const requests = [];
    const budgetPayload = {
      grams_per_month: '500.00', minutes_per_month: 600, minutes_per_coin: 1,
    };
    const approvalPayload = {
      estimated_grams: '12.50', estimated_minutes: 61,
      notes: 'Estimate checked in the slicer',
    };
    server.use(
      http.patch('*/api/print-budgets/:budgetId/', async ({ params, request }) => {
        expect(request.headers.get('Authorization')).toBe('Token test-session');
        requests.push({ action: 'budget', id: params.budgetId, body: await request.json() });
        return HttpResponse.json(budget);
      }),
      http.post('*/api/print-requests/:requestId/approve/', async ({ params, request }) => {
        requests.push({ action: 'approve', id: params.requestId, body: await request.json() });
        return HttpResponse.json(quoted);
      }),
    );
    expect(await updatePrintBudget(budget.id, budgetPayload)).toEqual(budget);
    const savedQuote = await approvePrintRequest(quoted.id, approvalPayload);
    expect(savedQuote).toEqual(quoted);
    expect(savedQuote).toMatchObject({
      status: 'quoted', estimated_grams: '12.50', estimated_minutes: 61,
      minutes_per_coin_snapshot: 1, coin_cost: 61, coins_paid: 0, coins_refunded: 0,
    });
    expect(requests).toEqual([
      { action: 'budget', id: String(budget.id), body: budgetPayload },
      { action: 'approve', id: String(quoted.id), body: approvalPayload },
    ]);
  });

  it('reads the frozen offer and posts only the request identity when paying and cancelling', async () => {
    const actions = [];
    server.use(
      http.get('*/api/print-requests/', ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get('status')).toBe('quoted');
        expect(request.headers.get('Authorization')).toBe('Token test-session');
        return HttpResponse.json(requestsQuoted);
      }),
      http.post('*/api/print-requests/:requestId/exchange/', async ({ params, request }) => {
        expect(request.headers.get('Authorization')).toBe('Token test-session');
        actions.push({ action: 'exchange', id: params.requestId, body: await request.json() });
        return HttpResponse.json(paid);
      }),
      http.post('*/api/print-requests/:requestId/cancel/', async ({ params, request }) => {
        actions.push({ action: 'cancel', id: params.requestId, body: await request.text() });
        return HttpResponse.json(refunded);
      }),
    );
    const offers = await listPrintRequests({ status: 'quoted' });
    expect(offers).toEqual(requestsQuoted);
    expect(offers.results).toEqual([quoted]);
    const confirmed = await exchangePrintRequest(quoted.id);
    expect(confirmed).toEqual(paid);
    expect(confirmed).toMatchObject({
      status: 'approved', coin_cost: 61, minutes_per_coin_snapshot: 1,
      coins_paid: 61, coins_refunded: 0,
    });
    const cancelled = await cancelPrintRequest(quoted.id);
    expect(cancelled).toEqual(refunded);
    expect(cancelled).toMatchObject({
      status: 'cancelled', coin_cost: 61, coins_paid: 61, coins_refunded: 61,
    });
    expect(actions).toEqual([
      { action: 'exchange', id: String(quoted.id), body: {} },
      { action: 'cancel', id: String(quoted.id), body: '' },
    ]);
  });

  it.each([
    ['invalid saved-price request', 400, invalidExchange],
    ['another account request', 404, notOwned],
  ])('preserves the %s error body and never retries a rejected spend', async (_name, status, response) => {
    const requests = [];
    server.use(http.post('*/api/print-requests/:requestId/exchange/', async ({ params, request }) => {
      requests.push({ id: params.requestId, body: await request.json() });
      return HttpResponse.json(response, { status });
    }));
    await expect(exchangePrintRequest(quoted.id)).rejects.toMatchObject({ status, response });
    expect(requests).toEqual([{ id: String(quoted.id), body: {} }]);
  });
});
