import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import idleClock from '../../../contracts/api/fixtures/clock-idle.json';
import activeClock from '../../../contracts/api/fixtures/clock-active.json';
import loginResponse from '../../../contracts/api/fixtures/auth-login-child.json';
import meResponse from '../../../contracts/api/fixtures/auth-me-child.json';
import firstPage from '../../../contracts/api/fixtures/habits-page-1.json';
import lastPage from '../../../contracts/api/fixtures/habits-page-2.json';
import emptyPage from '../../../contracts/api/fixtures/habits-empty.json';
import notificationsFirstPage from '../../../contracts/api/fixtures/notifications-page-1.json';
import notificationsLastPage from '../../../contracts/api/fixtures/notifications-page-2.json';
import notificationsEmptyPage from '../../../contracts/api/fixtures/notifications-empty.json';
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
import closedTimecard from '../../../contracts/api/fixtures/timecard-closed.json';
import closedTimecardDetail from '../../../contracts/api/fixtures/timecard-closed-detail.json';
import stableResponse from '../../../contracts/api/fixtures/pets-stable.json';
import emptyStable from '../../../contracts/api/fixtures/pets-stable-empty.json';
import restrictedEmptyStable from '../../../contracts/api/fixtures/pets-stable-restricted-empty.json';
import inventoryResponse from '../../../contracts/api/fixtures/inventory-food.json';
import emptyInventory from '../../../contracts/api/fixtures/inventory-empty.json';
import confirmedFeed from '../../../contracts/api/fixtures/pet-feed.json';
import neutralFeed from '../../../contracts/api/fixtures/pet-feed-neutral.json';
import evolvedFeed from '../../../contracts/api/fixtures/pet-feed-evolved.json';
import activatedPet from '../../../contracts/api/fixtures/pet-activate.json';
import activatedMount from '../../../contracts/api/fixtures/mount-activate.json';
import missingFood from '../../../contracts/api/fixtures/pet-feed-missing-food.json';
import unavailableFood from '../../../contracts/api/fixtures/pet-feed-unavailable-food.json';
import alreadyEvolved from '../../../contracts/api/fixtures/pet-feed-already-evolved.json';
import foreignPet from '../../../contracts/api/fixtures/pet-not-owned.json';
import foreignMount from '../../../contracts/api/fixtures/mount-not-owned.json';
import hatchingInventory from '../../../contracts/api/fixtures/inventory-hatching.json';
import hatchedPet from '../../../contracts/api/fixtures/pet-hatch.json';
import missingHatchIngredients from '../../../contracts/api/fixtures/pet-hatch-missing-ingredients.json';
import unavailableHatchEgg from '../../../contracts/api/fixtures/pet-hatch-unavailable-egg.json';
import unavailableHatchPotion from '../../../contracts/api/fixtures/pet-hatch-unavailable-potion.json';
import duplicateHatch from '../../../contracts/api/fixtures/pet-hatch-duplicate.json';
import shortExpedition from '../../../contracts/api/fixtures/expedition-start-short.json';
import standardExpedition from '../../../contracts/api/fixtures/expedition-start-standard.json';
import longExpedition from '../../../contracts/api/fixtures/expedition-start-long.json';
import allExpeditions from '../../../contracts/api/fixtures/expeditions.json';
import readyExpeditions from '../../../contracts/api/fixtures/expeditions-ready.json';
import emptyExpeditions from '../../../contracts/api/fixtures/expeditions-empty.json';
import claimedExpeditionHistory from '../../../contracts/api/fixtures/expeditions-claimed.json';
import expiredExpeditionHistory from '../../../contracts/api/fixtures/expeditions-expired.json';
import readyClaimExpedition from '../../../contracts/api/fixtures/expeditions-ready-claim.json';
import readySalvageExpedition from '../../../contracts/api/fixtures/expeditions-ready-salvage.json';
import expeditionStable from '../../../contracts/api/fixtures/pets-stable-expeditions.json';
import restedExpeditionStable from '../../../contracts/api/fixtures/pets-stable-expedition-rested.json';
import nextDayExpeditionStable from '../../../contracts/api/fixtures/pets-stable-expedition-next-day.json';
import claimedExpedition from '../../../contracts/api/fixtures/expedition-claim.json';
import repeatedExpeditionClaim from '../../../contracts/api/fixtures/expedition-claim-repeat.json';
import boostedExpeditionClaim from '../../../contracts/api/fixtures/expedition-claim-boosted.json';
import salvageExpeditionClaim from '../../../contracts/api/fixtures/expedition-claim-salvage.json';
import archivedItemExpeditionClaim from '../../../contracts/api/fixtures/expedition-claim-archived-item.json';
import invalidExpeditionTier from '../../../contracts/api/fixtures/expedition-invalid-tier.json';
import foreignExpeditionMount from '../../../contracts/api/fixtures/expedition-mount-not-owned.json';
import foreignExpedition from '../../../contracts/api/fixtures/expedition-not-owned.json';
import earlyExpeditionClaim from '../../../contracts/api/fixtures/expedition-early-claim.json';
import activeExpedition from '../../../contracts/api/fixtures/expedition-already-active.json';
import dailyExpeditionLimit from '../../../contracts/api/fixtures/expedition-daily-limit.json';
import expiredExpedition from '../../../contracts/api/fixtures/expedition-expired.json';
import breedingStable from '../../../contracts/api/fixtures/pets-stable-breeding.json';
import bredStable from '../../../contracts/api/fixtures/pets-stable-breeding-after.json';
import bredInventory from '../../../contracts/api/fixtures/inventory-breeding.json';
import bredMounts from '../../../contracts/api/fixtures/mount-breed.json';
import chromaticBreed from '../../../contracts/api/fixtures/mount-breed-chromatic.json';
import fallbackBreed from '../../../contracts/api/fixtures/mount-breed-fallback.json';
import missingBreedParents from '../../../contracts/api/fixtures/mount-breed-missing-mounts.json';
import sameBreedParent from '../../../contracts/api/fixtures/mount-breed-same-mount.json';
import invalidBreedParents from '../../../contracts/api/fixtures/mount-breed-invalid-ids.json';
import foreignBreedParent from '../../../contracts/api/fixtures/mount-breed-not-owned.json';
import restingBreedParent from '../../../contracts/api/fixtures/mount-breed-cooldown.json';
import repeatedBreed from '../../../contracts/api/fixtures/mount-breed-repeat-cooldown.json';
import { server } from '../test/server';
import { normalizeList } from '../utils/api';
import { api, getToken, setToken } from './client';
import {
  activateMount, activatePet, breedMounts, claimExpedition, closeTimecard, feedPet, getGreenlightOverview, getHabits, getInventory, getTimecard,
  getClockStatus, getMe, getNotifications, getStable, hatchPet, listExpeditions, logHabitTap, login,
  previewGreenlightCsv, reconcileGreenlightCsv, recordGreenlightPayout, saveGreenlightSnapshot, startExpedition,
} from './index';

// These are the raw response files checked against Django views and loaded
// directly by Unity. Do not replace them with a second client-specific factory.
describe('shared Django response fixtures through the React API client', () => {
  it('reads JSON null as an idle clock and preserves the active entry', async () => {
    let clock = idleClock;
    server.use(http.get('*/api/clock/', () => HttpResponse.json(clock)));

    expect(await getClockStatus()).toBeNull();
    clock = activeClock;
    expect(await getClockStatus()).toEqual(activeClock);
    expect(activeClock).toMatchObject({ status: 'active' });
    clock = idleClock;
    expect(await getClockStatus()).toBeNull();
  });

  it('preserves the confirmed zero-dollar timecard closure and later detail read', async () => {
    const calls = [];
    server.use(
      http.post('*/api/timecards/13/close/', async ({ request }) => {
        calls.push({ method: request.method, body: await request.json() });
        return HttpResponse.json(closedTimecard);
      }),
      http.get('*/api/timecards/13/', () => HttpResponse.json(closedTimecardDetail)),
    );
    expect(await closeTimecard(13)).toEqual(closedTimecard);
    expect(calls).toEqual([{ method: 'POST', body: {} }]);
    const detail = await getTimecard(13);
    expect(detail).toEqual(closedTimecardDetail);
    expect(detail).toMatchObject({ status: 'closed', total_hours: '0.10', total_earnings: '0.00' });
  });
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

  it('follows relative notification pages with the current session without marking updates read', async () => {
    const requests = [];
    setToken(loginResponse.token);
    server.use(http.all(/\/api\/notifications\//, ({ request }) => {
      const url = new URL(request.url);
      requests.push({ method: request.method, url, authorization: request.headers.get('authorization') });
      return HttpResponse.json(url.searchParams.get('page') === '2'
        ? notificationsLastPage : notificationsFirstPage);
    }));

    const page = await getNotifications();
    expect(page).toEqual(notificationsFirstPage);
    expect(page.count).toBe(21);
    expect(page.next).toMatch(/^\/api\/notifications\/\?/);
    expect(normalizeList(page)).toHaveLength(20);
    expect(page.results[0]).toMatchObject({
      id: 101, title: 'Fixture update 01', message: 'A synthetic saved update.',
      notification_type: 'drop_received', is_read: false, link: '/inventory',
    });
    const continuationPath = page.next.replace(/^\/api/, '');
    const final = await api.get(continuationPath);
    expect(final).toEqual(notificationsLastPage);
    expect(normalizeList(final)).toHaveLength(1);
    expect(final.next).toBeNull();
    expect(final.previous).toMatch(/^\/api\/notifications\/\?/);
    expect([...normalizeList(page), ...normalizeList(final)].map((notification) => notification.id)).toEqual(
      Array.from({ length: 21 }, (_, index) => index + 101),
    );
    expect([...normalizeList(page), ...normalizeList(final)].every((notification) => !notification.is_read)).toBe(true);

    setToken('replacement-notification-session');
    expect(await api.get(continuationPath)).toEqual(notificationsLastPage);
    const inheritedNamespace = new URL(page.next, window.location.origin).searchParams.get('_abby_session');
    const namespaces = requests.map(({ url }) => url.searchParams.get('_abby_session'));
    expect(inheritedNamespace).toBe('0123456789abcdef0123456789abcdef');
    expect(namespaces[0]).toBeTruthy();
    expect(namespaces[1]).toBe(namespaces[0]);
    expect(namespaces[2]).not.toBe(namespaces[0]);
    for (const { url } of requests) {
      expect(url.pathname).toBe('/api/notifications/');
      expect(url.searchParams.getAll('_abby_session')).toHaveLength(1);
      expect(url.searchParams.get('_abby_session')).not.toBe(inheritedNamespace);
    }
    expect(requests.map(({ method }) => method)).toEqual(['GET', 'GET', 'GET']);
    expect(requests.map(({ url }) => url.searchParams.get('page'))).toEqual([null, '2', '2']);
    expect(requests.map(({ authorization }) => authorization)).toEqual([
      `Token ${loginResponse.token}`, `Token ${loginResponse.token}`, 'Token replacement-notification-session',
    ]);
  });

  it('normalizes the empty notification pagination envelope', async () => {
    server.use(http.get('*/api/notifications/', () => HttpResponse.json(notificationsEmptyPage)));
    const page = await getNotifications();
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

  it('reads owned pets, mounts and the raw inventory array without losing nested care fields', async () => {
    const authorizations = [];
    setToken(loginResponse.token);
    server.use(
      http.get('*/api/pets/stable/', ({ request }) => {
        authorizations.push(request.headers.get('authorization'));
        return HttpResponse.json(stableResponse);
      }),
      http.get('*/api/inventory/', ({ request }) => {
        authorizations.push(request.headers.get('authorization'));
        return HttpResponse.json(inventoryResponse);
      }),
    );

    const stable = await getStable();
    const inventory = await getInventory();
    expect(stable).toEqual(stableResponse);
    expect(inventory).toEqual(inventoryResponse);
    expect(stable.pets[0]).toMatchObject({
      id: 51, name: 'Sprout {a} "friend"', growth_points: 20, is_active: true,
      evolved_to_mount: false, happiness_level: 'happy', last_fed_at: null,
      species: { id: 41, name: 'Fox', sprite_key: 'fox' },
      potion: { id: 43, slug: 'fire', rarity: 'uncommon' },
    });
    expect(stable.pets.find((pet) => pet.id === 52)).toMatchObject({
      happiness_level: 'stale', last_fed_at: '2026-10-01T12:00:00-07:00',
    });
    expect(stable.pets.find((pet) => pet.id === 53)).toMatchObject({
      growth_points: 100, evolved_to_mount: true, is_fully_grown: true,
    });
    expect(stable.mounts[0]).toMatchObject({
      id: 61, is_active: true, active_expedition: null, can_breed: false, breeding_cooldown_seconds: 0,
    });
    expect(stable.mounts.find((mount) => mount.id === 62)).toMatchObject({
      can_breed: false, breeding_cooldown_seconds: 432000,
    });
    const foods = normalizeList(inventory).filter((entry) => entry.item.item_type === 'food');
    expect(foods.map((entry) => entry.item.id)).toEqual([71, 72, 74]);
    expect(foods[0]).toMatchObject({
      id: 81, quantity: 2, item: { id: 71, food_species_name: 'Fox' },
      available_actions: [{ id: 'feed', label: 'Feed a companion', to: '/bestiary?tab=companions' }],
    });
    expect(foods[1].item.food_species_name).toBeNull();
    expect(authorizations).toEqual([`Token ${loginResponse.token}`, `Token ${loginResponse.token}`]);
  });

  it('preserves empty collection totals and the empty inventory array', async () => {
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json(emptyStable)),
      http.get('*/api/inventory/', () => HttpResponse.json(emptyInventory)),
    );
    expect(await getStable()).toEqual({ pets: [], mounts: [], total_pets: 0, total_mounts: 0, total_possible: 4, breeding_available: false });
    expect(normalizeList(await getInventory())).toEqual([]);
  });

  it('preserves the supported species/potion total without inventing owned companions', async () => {
    server.use(http.get('*/api/pets/stable/', () => HttpResponse.json(restrictedEmptyStable)));
    const stable = await getStable();
    expect(stable).toEqual(restrictedEmptyStable);
    expect(stable).toEqual({ pets: [], mounts: [], total_pets: 0, total_mounts: 0, total_possible: 3, breeding_available: false });
  });

  it('reads hatching ingredients with their item definition IDs, quantities and nullable typed names', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json(hatchingInventory)));
    const inventory = normalizeList(await getInventory());
    expect(inventory).toEqual(hatchingInventory);
    const eggs = inventory.filter((entry) => entry.item.item_type === 'egg');
    const potions = inventory.filter((entry) => entry.item.item_type === 'potion');
    expect(eggs).toHaveLength(1);
    expect(eggs[0]).toMatchObject({
      id: 83, quantity: 2,
      item: { id: 73, pet_species_name: 'Fox', potion_type_name: null },
    });
    expect(potions.map((entry) => entry.item.id)).toEqual([76, 75]);
    expect(potions.find((entry) => entry.item.id === 75)).toMatchObject({
      id: 85, quantity: 1,
      item: { id: 75, potion_type_name: 'Ice', pet_species_name: null },
    });
  });

  it('hatches with actual egg and potion item IDs and preserves the complete HTTP 201 pet receipt', async () => {
    const calls = [];
    setToken(loginResponse.token);
    server.use(http.post('*/api/pets/hatch/', async ({ request }) => {
      calls.push({
        body: await request.json(), authorization: request.headers.get('authorization'),
        method: request.method, pathname: new URL(request.url).pathname,
      });
      return HttpResponse.json(hatchedPet, { status: 201 });
    }));

    const pet = await hatchPet(73, 75);
    expect(pet).toEqual(hatchedPet);
    expect(pet).toMatchObject({
      id: 83, name: '', growth_points: 0, is_active: false,
      evolved_to_mount: false, is_fully_grown: false, happiness_level: 'happy', last_fed_at: null,
      species: { id: 41, name: 'Fox', sprite_key: 'fox' },
      potion: { id: 44, name: 'Ice', slug: 'ice', sprite_key: 'ice-potion', rarity: 'rare' },
    });
    expect(calls).toEqual([{
      body: { egg_item_id: 73, potion_item_id: 75 },
      authorization: `Token ${loginResponse.token}`, method: 'POST', pathname: '/api/pets/hatch/',
    }]);
  });

  it.each([
    ['missing ingredients', undefined, undefined, {}, missingHatchIngredients],
    ['unavailable egg', 999, 75, { egg_item_id: 999, potion_item_id: 75 }, unavailableHatchEgg],
    ['unavailable potion', 73, 999, { egg_item_id: 73, potion_item_id: 999 }, unavailableHatchPotion],
    ['duplicate combination', 73, 76, { egg_item_id: 73, potion_item_id: 76 }, duplicateHatch],
  ])('preserves %s hatch rejection and does not replay the POST', async (_label, eggId, potionId, body, response) => {
    const submitted = [];
    server.use(http.post('*/api/pets/hatch/', async ({ request }) => {
      submitted.push(await request.json());
      return HttpResponse.json(response, { status: 400 });
    }));
    await expect(hatchPet(eggId, potionId)).rejects.toMatchObject({
      status: 400, message: response.error, response,
    });
    expect(submitted).toEqual([body]);
  });

  it.each([
    ['preferred food', 51, 71, confirmedFeed],
    ['neutral food', 51, 72, neutralFeed],
    ['evolving food', 52, 74, evolvedFeed],
  ])('sends the actual item definition ID for %s and preserves server-confirmed growth', async (_label, petId, foodId, response) => {
    let submitted;
    let authorization;
    setToken(loginResponse.token);
    server.use(http.post(`*/api/pets/${petId}/feed/`, async ({ request }) => {
      submitted = await request.json();
      authorization = request.headers.get('authorization');
      return HttpResponse.json(response);
    }));

    const result = await feedPet(petId, foodId);
    expect(submitted).toEqual({ food_item_id: foodId });
    expect(authorization).toBe(`Token ${loginResponse.token}`);
    expect(result).toEqual(response);
    expect(result.new_growth).toBe(response.new_growth);
    expect(result.evolved).toBe(response.evolved);
    expect(result.mount_id).toBe(response.mount_id);
  });

  it.each([
    ['short', 61, shortExpedition, 15, 1],
    ['standard', 62, standardExpedition, 35, 2],
    ['long', 63, longExpedition, 75, 3],
  ])('starts a %s expedition with the owned mount ID and preserves locked planned loot', async (tier, mountId, response, plannedCoins, slots) => {
    const calls = [];
    setToken(loginResponse.token);
    server.use(http.post(`*/api/mounts/${mountId}/expedition/`, async ({ request }) => {
      calls.push({
        body: await request.json(), authorization: request.headers.get('authorization'),
        method: request.method, pathname: new URL(request.url).pathname,
      });
      return HttpResponse.json(response, { status: 201 });
    }));

    const expedition = await startExpedition(mountId, tier);
    expect(expedition).toEqual(response);
    expect(expedition).toMatchObject({ mount_id: mountId, tier, status: 'active', is_ready: false, claimed_at: null });
    expect(expedition.seconds_remaining).toBeGreaterThan(0);
    expect(expedition.loot.coins).toBe(plannedCoins);
    expect(expedition.loot.items).toHaveLength(slots);
    expect(expedition.loot.items.map((slot) => slot.item_id)).toEqual(Array(slots).fill(71));
    expect(expedition).not.toHaveProperty('coins_awarded');
    expect(calls).toEqual([{
      body: { tier }, authorization: `Token ${loginResponse.token}`,
      method: 'POST', pathname: `/api/mounts/${mountId}/expedition/`,
    }]);
  });

  it.each([
    ['all expeditions', false, allExpeditions],
    ['ready expeditions', true, readyExpeditions],
    ['ready claim context', true, readyClaimExpedition],
    ['ready salvage context', true, readySalvageExpedition],
    ['claimed history', false, claimedExpeditionHistory],
    ['expired history', false, expiredExpeditionHistory],
    ['empty collection', false, emptyExpeditions],
  ])('reads %s through the raw expeditions envelope without claiming', async (_label, readyOnly, response) => {
    const calls = [];
    setToken(loginResponse.token);
    server.use(http.all('*/api/expeditions/', ({ request }) => {
      const url = new URL(request.url);
      calls.push({ method: request.method, ready: url.searchParams.get('ready'), authorization: request.headers.get('authorization') });
      return HttpResponse.json(response);
    }));
    expect(await listExpeditions(readyOnly)).toEqual(response);
    expect(calls).toEqual([{
      method: 'GET', ready: readyOnly ? 'true' : null, authorization: `Token ${loginResponse.token}`,
    }]);
    expect(response.expeditions.every((row) => row.mount_id >= 61 && row.mount_id <= 63)).toBe(true);
    if (readyOnly) {
      expect(response.expeditions.every((row) => row.status === 'active' && row.is_ready && row.seconds_remaining <= 0)).toBe(true);
    }
  });

  it('preserves stable mount expedition summaries with the same identities as the full list', async () => {
    server.use(http.get('*/api/pets/stable/', () => HttpResponse.json(expeditionStable)));
    const stable = await getStable();
    expect(stable).toEqual(expeditionStable);
    expect(stable.mounts.map((mount) => mount.active_expedition.id).sort()).toEqual([103, 104, 105]);
    for (const mount of stable.mounts) {
      expect(mount.active_expedition).toEqual(allExpeditions.expeditions.find((row) => row.mount_id === mount.id));
      expect(mount.expedition_available).toBe(false);
      expect(mount.expedition_available_at).toBeNull();
    }
  });

  it('keeps the server daily expedition rest separate from unclaimed trips and opens it the next day', async () => {
    server.use(http.get('*/api/pets/stable/', () => HttpResponse.json(restedExpeditionStable)));
    const rested = (await getStable()).mounts.find((mount) => mount.id === 61);
    expect(rested).toMatchObject({ active_expedition: null, expedition_available: false, expedition_available_at: '2026-10-11T00:00:00-07:00' });
    server.use(http.get('*/api/pets/stable/', () => HttpResponse.json(nextDayExpeditionStable)));
    expect((await getStable()).mounts.find((mount) => mount.id === 61)).toMatchObject({ active_expedition: null, expedition_available: true, expedition_available_at: null });
  });

  it.each([
    ['fresh claim', claimedExpedition, true, 15],
    ['repeat claim', repeatedExpeditionClaim, false, 0],
    ['boosted claim', boostedExpeditionClaim, true, 30],
    ['duplicate cosmetic salvage', salvageExpeditionClaim, true, 15],
    ['archived planned item', archivedItemExpeditionClaim, true, 15],
  ])('claims %s with an empty POST and preserves actual coins separately from planned item slots', async (_label, response, freshlyClaimed, actualCoins) => {
    const calls = [];
    setToken(loginResponse.token);
    server.use(http.post('*/api/expeditions/103/claim/', async ({ request }) => {
      calls.push({
        body: await request.text(), authorization: request.headers.get('authorization'),
        method: request.method, pathname: new URL(request.url).pathname,
      });
      return HttpResponse.json(response);
    }));
    const result = await claimExpedition(103);
    expect(result).toEqual(response);
    expect(result).toMatchObject({
      expedition_id: 103, tier: 'short', freshly_claimed: freshlyClaimed, coins_awarded: actualCoins,
      mount: { id: 61, species_name: 'Fox', species_slug: 'fixture-fox', potion_name: 'Ice', potion_slug: 'ice' },
    });
    expect(calls).toEqual([{
      body: '', authorization: `Token ${loginResponse.token}`, method: 'POST', pathname: '/api/expeditions/103/claim/',
    }]);
    if (!freshlyClaimed) expect(result.items).toEqual(claimedExpedition.items);
    if (result.items[0].salvaged_to_coins) {
      expect(result.items[0].salvaged_to_coins).toBe(20);
      expect(result.coins_awarded).toBe(15);
    }
  });

  it.each([
    ['invalid tier', '/api/mounts/61/expedition/', () => startExpedition(61, 'marathon'), 400, invalidExpeditionTier],
    ['foreign mount', '/api/mounts/81/expedition/', () => startExpedition(81, 'short'), 404, foreignExpeditionMount],
    ['foreign expedition', '/api/expeditions/101/claim/', () => claimExpedition(101), 404, foreignExpedition],
    ['early claim', '/api/expeditions/103/claim/', () => claimExpedition(103), 400, earlyExpeditionClaim],
    ['already active mount', '/api/mounts/61/expedition/', () => startExpedition(61, 'short'), 400, activeExpedition],
    ['daily limit', '/api/mounts/61/expedition/', () => startExpedition(61, 'short'), 400, dailyExpeditionLimit],
    ['expired expedition', '/api/expeditions/103/claim/', () => claimExpedition(103), 400, expiredExpedition],
  ])('exposes %s expedition rejection with its actual HTTP status and never replays the POST', async (_label, path, action, status, response) => {
    let calls = 0;
    server.use(http.post(`*${path}`, () => {
      calls += 1;
      return HttpResponse.json(response, { status });
    }));
    await expect(action()).rejects.toMatchObject({ status, message: response.error, response });
    expect(calls).toBe(1);
  });

  it('activates a pet and mount through their distinct endpoints with empty bodies', async () => {
    const calls = [];
    setToken(loginResponse.token);
    server.use(
      http.post('*/api/pets/52/activate/', async ({ request }) => {
        calls.push({ body: await request.text(), authorization: request.headers.get('authorization') });
        return HttpResponse.json(activatedPet);
      }),
      http.post('*/api/mounts/62/activate/', async ({ request }) => {
        calls.push({ body: await request.text(), authorization: request.headers.get('authorization') });
        return HttpResponse.json(activatedMount);
      }),
    );

    expect(await activatePet(52)).toEqual(activatedPet);
    expect(await activateMount(62)).toEqual(activatedMount);
    expect(activatedPet).toMatchObject({ id: 52, is_active: true, growth_points: 90 });
    expect(activatedMount).toMatchObject({
      id: 62, is_active: true, active_expedition: null, can_breed: false, breeding_cooldown_seconds: 432000,
    });
    expect(calls).toEqual([
      { body: '', authorization: `Token ${loginResponse.token}` },
      { body: '', authorization: `Token ${loginResponse.token}` },
    ]);
  });

  it('reads authoritative breeding eligibility, including an away parent and refreshed cooldowns', async () => {
    let response = breedingStable;
    const methods = [];
    server.use(http.all('*/api/pets/stable/', ({ request }) => {
      methods.push(request.method);
      return HttpResponse.json(response);
    }));
    const stable = await getStable();
    expect(stable).toEqual(breedingStable);
    expect(stable.mounts.find((mount) => mount.id === 61)).toMatchObject({
      can_breed: true, breeding_cooldown_seconds: 0, active_expedition: { id: 103, status: 'active' },
    });
    expect(stable.mounts.find((mount) => mount.id === 62)).toMatchObject({ can_breed: true, breeding_cooldown_seconds: 0 });
    expect(stable.mounts.find((mount) => mount.id === 63)).toMatchObject({ can_breed: false, breeding_cooldown_seconds: 432000 });
    response = bredStable;
    const refreshed = await getStable();
    expect(refreshed).toEqual(bredStable);
    expect(refreshed.mounts.filter((mount) => mount.id === 61 || mount.id === 62)
      .every((mount) => !mount.can_breed && mount.breeding_cooldown_seconds === 604800)).toBe(true);
    expect(methods).toEqual(['GET', 'GET']);
  });

  it('reads the bred egg and potion as confirmed inventory quantities without consuming existing food', async () => {
    server.use(http.get('*/api/inventory/', () => HttpResponse.json(bredInventory)));
    const inventory = normalizeList(await getInventory());
    expect(inventory).toEqual(bredInventory);
    expect(inventory.find((entry) => entry.item.id === 73)).toMatchObject({ quantity: 2, item: { item_type: 'egg', pet_species_name: 'Fox' } });
    expect(inventory.find((entry) => entry.item.id === 77)).toMatchObject({ quantity: 4, item: { item_type: 'potion', potion_type_name: 'Ice' } });
    expect(inventory.find((entry) => entry.item.id === 71).quantity).toBe(2);
  });

  it.each([
    ['normal pair', bredMounts, 77, 'Ice', false],
    ['chromatic pair', chromaticBreed, 78, 'Cosmic', true],
    ['registered compatible fallback', fallbackBreed, 79, 'Base', false],
  ])('breeds %s through one authenticated parent-ID POST and preserves the full HTTP 201 receipt', async (_label, response, potionId, potionName, chromatic) => {
    const calls = [];
    setToken(loginResponse.token);
    server.use(http.post('*/api/mounts/breed/', async ({ request }) => {
      calls.push({ body: await request.json(), authorization: request.headers.get('authorization'), method: request.method, pathname: new URL(request.url).pathname });
      return HttpResponse.json(response, { status: 201 });
    }));
    const result = await breedMounts(61, 62);
    expect(result).toEqual(response);
    expect(result).toMatchObject({
      egg_item_id: 73, potion_item_id: potionId, picked_species: 'Fox', picked_species_slug: 'fixture-fox',
      picked_potion: potionName, chromatic, cooldown_days: 7,
    });
    expect(result).not.toHaveProperty('coins_awarded');
    expect(result).not.toHaveProperty('xp_awarded');
    expect(calls).toEqual([{
      body: { mount_a_id: 61, mount_b_id: 62 }, authorization: `Token ${loginResponse.token}`,
      method: 'POST', pathname: '/api/mounts/breed/',
    }]);
  });

  it.each([
    ['missing parents', undefined, undefined, {}, missingBreedParents],
    ['same parent', 61, 61, { mount_a_id: 61, mount_b_id: 61 }, sameBreedParent],
    ['invalid parent ID', 'invalid', 62, { mount_a_id: 'invalid', mount_b_id: 62 }, invalidBreedParents],
    ['foreign parent', 61, 81, { mount_a_id: 61, mount_b_id: 81 }, foreignBreedParent],
    ['resting parent', 61, 63, { mount_a_id: 61, mount_b_id: 63 }, restingBreedParent],
    ['repeat within cooldown', 61, 62, { mount_a_id: 61, mount_b_id: 62 }, repeatedBreed],
  ])('preserves %s breeding rejection and never automatically replays the POST', async (_label, parentA, parentB, expectedBody, response) => {
    const bodies = [];
    server.use(http.post('*/api/mounts/breed/', async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json(response, { status: 400 });
    }));
    await expect(breedMounts(parentA, parentB)).rejects.toMatchObject({ status: 400, message: response.error, response });
    expect(bodies).toEqual([expectedBody]);
  });

  it.each([
    ['missing food', '/api/pets/51/feed/', () => feedPet(51), missingFood],
    ['unavailable food', '/api/pets/51/feed/', () => feedPet(51, 999), unavailableFood],
    ['already evolved pet', '/api/pets/53/feed/', () => feedPet(53, 71), alreadyEvolved],
    ['foreign pet feed', '/api/pets/81/feed/', () => feedPet(81, 71), foreignPet],
    ['foreign pet activation', '/api/pets/81/activate/', () => activatePet(81), foreignPet],
    ['foreign mount activation', '/api/mounts/81/activate/', () => activateMount(81), foreignMount],
  ])('exposes %s rejection with the actual HTTP status and response', async (_label, path, action, response) => {
    server.use(http.post(`*${path}`, () => HttpResponse.json(response, { status: 400 })));
    await expect(action()).rejects.toMatchObject({ status: 400, message: response.error, response });
  });
});
