import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import loginResponse from '../../../contracts/api/fixtures/auth-login-child.json';
import meResponse from '../../../contracts/api/fixtures/auth-me-child.json';
import firstPage from '../../../contracts/api/fixtures/habits-page-1.json';
import lastPage from '../../../contracts/api/fixtures/habits-page-2.json';
import emptyPage from '../../../contracts/api/fixtures/habits-empty.json';
import confirmedTap from '../../../contracts/api/fixtures/habit-positive-tap.json';
import tapWithoutEvent from '../../../contracts/api/fixtures/habit-positive-tap-no-event.json';
import rejectedTap from '../../../contracts/api/fixtures/habit-positive-tap-limit.json';
import greenlightUnknown from '../../../contracts/api/fixtures/greenlight-overview-no-snapshot.json';
import greenlightOverview from '../../../contracts/api/fixtures/greenlight-overview.json';
import greenlightSnapshot from '../../../contracts/api/fixtures/greenlight-balance-snapshot.json';
import greenlightPayout from '../../../contracts/api/fixtures/greenlight-payout.json';
import greenlightPreview from '../../../contracts/api/fixtures/greenlight-preview.json';
import greenlightReconciled from '../../../contracts/api/fixtures/greenlight-reconcile.json';
import greenlightFinal from '../../../contracts/api/fixtures/greenlight-overview-reconciled.json';
import { server } from '../test/server';
import { normalizeList } from '../utils/api';
import { api, getToken, setToken } from './client';
import {
  getGreenlightOverview, getHabits, getMe, logHabitTap, login,
  previewGreenlightCsv, reconcileGreenlightCsv, recordGreenlightPayout, saveGreenlightSnapshot,
} from './index';

// These are the raw response files checked against Django views and loaded
// directly by Unity. Do not replace them with a second client-specific factory.
describe('shared Django response fixtures through the React API client', () => {
  it('accepts the flat login response and uses its token to verify the same child', async () => {
    setToken(null);
    let submitted;
    let loginAuthorization;
    let meAuthorization;
    server.use(
      http.post('*/api/auth/', async ({ request }) => {
        submitted = await request.json();
        loginAuthorization = request.headers.get('authorization');
        return HttpResponse.json(loginResponse);
      }),
      http.get('*/api/auth/me/', ({ request }) => {
        meAuthorization = request.headers.get('authorization');
        return HttpResponse.json(meResponse);
      }),
    );

    const authenticated = await login('fixture-child', 'synthetic-password');
    expect(submitted).toEqual({ action: 'login', username: 'fixture-child', password: 'synthetic-password' });
    expect(loginAuthorization).toBeNull();
    expect(authenticated).toEqual(loginResponse);
    expect(getToken()).toBe(loginResponse.token);
    expect(await getMe()).toEqual(meResponse);
    expect(meAuthorization).toBe(`Token ${loginResponse.token}`);
    expect(authenticated.id).toBe(meResponse.id);
    expect(meResponse.role).toBe('child');
    expect(meResponse.family.id).toBe(1);
    expect(meResponse).not.toHaveProperty('token');
  });

  it('reads populated pages without losing identity, safety flags or nested skill tags', async () => {
    const requestedPages = [];
    server.use(http.get('*/api/habits/', ({ request }) => {
      const page = new URL(request.url).searchParams.get('page');
      requestedPages.push(page);
      return HttpResponse.json(page === '2' ? lastPage : firstPage);
    }));

    const page = await getHabits();
    expect(page).toEqual(firstPage);
    const habits = normalizeList(page);
    expect(habits).toHaveLength(20);
    expect(habits[0]).toMatchObject({
      id: 9, user: 7, name: 'Read {a} book "today"',
      strength: -2, taps_today: 0, is_active: true, pending_parent_review: false,
      skill_tags: [{ skill: 2, skill_name: 'Reading', skill_category: 'Language Arts', xp_weight: 1 }],
    });
    expect(habits[1].habit_type).toBe('negative');
    expect(habits[2].habit_type).toBe('both');
    expect(habits[3].is_active).toBe(false);
    const final = await api.get(`/habits/${new URL(page.next).search}`);
    expect(final).toEqual(lastPage);
    expect(normalizeList(final)).toHaveLength(1);
    expect(final.next).toBeNull();
    expect([...habits, ...normalizeList(final)].map((habit) => habit.id)).toEqual(
      Array.from({ length: 21 }, (_, index) => index + 9),
    );
    expect(requestedPages).toEqual([null, '2']);
  });

  it('normalizes an empty real pagination envelope', async () => {
    server.use(http.get('*/api/habits/', () => HttpResponse.json(emptyPage)));
    const page = await getHabits();
    expect(page).toEqual({ count: 0, next: null, previous: null, results: [] });
    expect(normalizeList(page)).toEqual([]);
  });

  it('sends an authenticated positive tap and preserves the confirmed game event', async () => {
    let submitted;
    let authorization;
    setToken(loginResponse.token);
    server.use(http.post('*/api/habits/9/log/', async ({ request }) => {
      submitted = await request.json();
      authorization = request.headers.get('authorization');
      return HttpResponse.json(confirmedTap);
    }));

    const result = await logHabitTap(9, 1);
    expect(submitted).toEqual({ direction: 1 });
    expect(authorization).toBe(`Token ${loginResponse.token}`);
    expect(result).toEqual(confirmedTap);
    expect(result.new_strength).toBe(-1);
    expect(result.game_event.streak).toMatchObject({ is_first_today: true, streak: 1, check_in_bonus_coins: 5 });
    expect(result.game_event.daily_challenge).toMatchObject({ progress: 1, target: 2, newly_completed: false });
    expect(result.game_event.quest).toBeNull();
    expect(result.game_event.drops).toEqual([]);
  });

  it('retains confirmation when the optional game event is null', async () => {
    server.use(http.post('*/api/habits/9/log/', () => HttpResponse.json(tapWithoutEvent)));
    const result = await logHabitTap(9, 1);
    expect(result).toEqual({ direction: 1, xp_reward: 5, new_strength: -1, game_event: null });
  });

  it('exposes the real daily-limit rejection as an error with its HTTP status and response', async () => {
    let calls = 0;
    server.use(http.post('*/api/habits/9/log/', () => {
      calls += 1;
      return calls === 1
        ? HttpResponse.json(confirmedTap)
        : HttpResponse.json(rejectedTap, { status: 400 });
    }));

    await expect(logHabitTap(9, 1)).resolves.toMatchObject({ direction: 1, new_strength: -1 });
    await expect(logHabitTap(9, 1)).rejects.toMatchObject({
      status: 400, message: 'Daily limit reached (1 taps/day).', response: rejectedTap,
    });
    expect(calls).toBe(2);
  });

  it('keeps money owed and the separately reported Greenlight balance distinct, including unknown balance', async () => {
    const children = [];
    let response = greenlightUnknown;
    server.use(http.get('*/api/payments/greenlight/overview/', ({ request }) => {
      children.push(new URL(request.url).searchParams.get('user_id'));
      return HttpResponse.json(response);
    }));

    const unknown = await getGreenlightOverview(7);
    expect(unknown).toEqual(greenlightUnknown);
    expect(unknown).toMatchObject({
      user_id: 7, owed_balance: '25.00', approved_payable: '20.00', pending_hourly: '5.00',
      balance_snapshot: null,
    });
    response = greenlightOverview;
    const reported = await getGreenlightOverview(7);
    expect(reported).toEqual(greenlightOverview);
    expect(reported.balance_snapshot).toEqual(greenlightSnapshot);
    expect(reported.balance_snapshot.amount).toBe('40.25');
    expect(Date.parse(reported.balance_snapshot.as_of)).toBe(Date.parse('2026-10-11T18:00:00Z'));
    expect(reported.owed_balance).toBe(unknown.owed_balance);
    expect(children).toEqual(['7', '7']);
  });

  it('records a parent-confirmed payout with its retry identity and a separate balance snapshot', async () => {
    const submitted = [];
    setToken(loginResponse.token);
    server.use(
      http.post('*/api/payments/greenlight/payout/', async ({ request }) => {
        submitted.push({ body: await request.json(), authorization: request.headers.get('authorization') });
        return HttpResponse.json(greenlightPayout, { status: 201 });
      }),
      http.post('*/api/payments/greenlight/snapshot/', async ({ request }) => {
        submitted.push({ body: await request.json(), authorization: request.headers.get('authorization') });
        return HttpResponse.json(greenlightSnapshot, { status: 201 });
      }),
    );
    const payoutRequest = {
      user_id: 7, amount: '12.50', transferred_on: '2026-10-11',
      reference: 'fixture-week-1', memo: 'Transferred after approval', timecard_id: 11,
      idempotency_key: '11111111-1111-4111-8111-111111111111',
    };
    const snapshotRequest = {
      user_id: 7, amount: '40.25', as_of: '2026-10-11T18:00:00Z', memo: 'Checked in the Greenlight app',
    };
    expect(await recordGreenlightPayout(payoutRequest)).toEqual(greenlightPayout);
    expect(greenlightPayout.payout).toMatchObject({
      amount: '12.50', timecard: 11, source: 'manual', reconciled: false,
    });
    expect(await saveGreenlightSnapshot(snapshotRequest)).toEqual(greenlightSnapshot);
    expect(submitted).toEqual([
      { body: payoutRequest, authorization: `Token ${loginResponse.token}` },
      { body: snapshotRequest, authorization: `Token ${loginResponse.token}` },
    ]);
  });

  it('previews statement rows, matches an existing payout and records only the selected new transfer', async () => {
    const submitted = [];
    server.use(
      http.post('*/api/payments/greenlight/preview/', async ({ request }) => {
        submitted.push(await request.json());
        return HttpResponse.json(greenlightPreview);
      }),
      http.post('*/api/payments/greenlight/reconcile/', async ({ request }) => {
        submitted.push(await request.json());
        return HttpResponse.json(greenlightReconciled);
      }),
      http.get('*/api/payments/greenlight/overview/', () => HttpResponse.json(greenlightFinal)),
    );
    const csv_data = 'date,amount,description,reference,type\n'
      + '2026-10-11,12.50,Weekly project payout,fixture-week-1,transfer\n'
      + '2026-10-11,7.50,Approved chore payout,fixture-chore-1,transfer\n'
      + '2026-10-11,-3.00,Bookshop purchase,fixture-purchase-1,purchase\n';
    const previewRequest = { user_id: 7, csv_data };
    const preview = await previewGreenlightCsv(previewRequest);
    expect(preview).toEqual(greenlightPreview);
    expect(preview.rows[0]).toMatchObject({ eligible: true, match_candidates: [greenlightPayout.payout.id] });
    expect(preview.rows[1]).toMatchObject({ eligible: true, amount: '7.50' });
    expect(preview.rows[2]).toMatchObject({ eligible: false, amount: '-3.00' });
    const reconcileRequest = {
      ...previewRequest,
      selections: [
        { fingerprint: preview.rows[0].fingerprint, match_payment_id: greenlightPayout.payout.id },
        { fingerprint: preview.rows[1].fingerprint },
      ],
    };
    expect(await reconcileGreenlightCsv(reconcileRequest)).toEqual({ recorded: 1, matched: 1, duplicates: 0 });
    expect(submitted).toEqual([previewRequest, reconcileRequest]);
    const final = await getGreenlightOverview(7);
    expect(final).toEqual(greenlightFinal);
    expect(final).toMatchObject({ owed_balance: '5.00', approved_payable: '0.00', pending_hourly: '5.00' });
    expect(final.balance_snapshot).toEqual(greenlightSnapshot);
    expect(final.payouts).toHaveLength(2);
    expect(final.payouts.every((payout) => payout.reconciled)).toBe(true);
  });
});
