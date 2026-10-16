import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Rewards from './Rewards.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildParent, buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(user = buildUser(), handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Rewards />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Rewards', () => {
  it.each([
    ['/api/redemptions/', '/api/redemptions/21/approve/', 'Reward request history', 'reward requests'],
    ['/api/coins/exchange/list/', '/api/coins/exchange/21/approve/', 'Exchange history', 'exchanges'],
  ])('allows approval on the second pending page of %s while keeping history separate', async (path, approvePath, historyTitle, noun) => {
    const user = userEvent.setup();
    const row = (id, status = 'pending') => ({
      id, user: 2, user_name: id === 21 ? 'Older request' : 'Abby', status,
      reward: { name: id === 21 ? 'Older toy' : `Toy ${id}`, icon: '🎁' },
      coin_cost_snapshot: 80, requested_at: '2026-04-15T12:00:00Z',
      dollar_amount: '5.00', coin_amount: 50, exchange_rate: 10, created_at: '2026-04-15T12:00:00Z',
    });
    const reads = spyHandler('get', `*${path}`, ({ request }) => {
      const url = new URL(request.url);
      if (!url.searchParams.has('status')) {
        return { count: 41, next: `http://localhost${path}?page=2`, results: Array.from({ length: 20 }, (_, i) => row(i + 101, 'fulfilled')) };
      }
      expect(url.searchParams.get('status')).toBe('pending');
      return url.searchParams.get('page') === '2'
        ? { count: 21, next: null, results: [row(21)] }
        : { count: 21, next: `http://localhost${path}?status=pending&page=2`, results: Array.from({ length: 20 }, (_, i) => row(i + 1)) };
    });
    const approve = spyHandler('post', `*${approvePath}`, { id: 21, status: 'fulfilled' });
    renderPage(buildParent(), [
      reads.handler, approve.handler,
      http.get('*/api/rewards/', () => HttpResponse.json([])),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
    ]);

    await waitFor(() => expect(screen.getAllByRole('button', { name: /^approve$/i })).toHaveLength(21));
    expect(reads.calls).toHaveLength(3);
    expect(reads.calls.some(({ url }) => new URL(url).searchParams.get('page') === '2')).toBe(true);
    expect(reads.calls.filter(({ url }) => new URL(url).searchParams.has('page')).every(({ url }) => new URL(url).searchParams.get('status') === 'pending')).toBe(true);
    await user.click(screen.getAllByRole('button', { name: /^approve$/i })[20]);
    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(new URL(approve.calls[0].url).pathname).toBe(approvePath);
    expect(approve.calls[0].body).toEqual({ notes: '' });

    await user.click(screen.getByRole('button', { name: new RegExp(historyTitle, 'i') }));
    expect(await screen.findByText(`Showing the 20 most recent of 41 ${noun}.`)).toBeInTheDocument();
  });

  it('shows a retry when a later pending page fails and does not expose a partial approval queue', async () => {
    const user = userEvent.setup();
    let failSecondPage = true;
    const reads = spyHandler('get', '*/api/redemptions/', ({ request }) => {
      const url = new URL(request.url);
      if (!url.searchParams.has('status')) return [];
      const row = { id: 22, user_name: 'Abby', status: 'pending', reward: { name: 'Recovered toy', icon: '🎁' }, coin_cost_snapshot: 80 };
      if (url.searchParams.has('page')) {
        if (failSecondPage) {
          failSecondPage = false;
          return HttpResponse.json({ detail: 'Temporary queue failure' }, { status: 503 });
        }
        return { count: 2, next: null, results: [{ ...row, id: 23 }] };
      }
      return { count: 2, next: 'http://localhost/api/redemptions/?status=pending&page=2', results: [row] };
    });
    renderPage(buildParent(), [reads.handler]);
    expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load pending reward requests. Temporary queue failure");
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(screen.getAllByRole('button', { name: /^approve$/i })).toHaveLength(2));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(reads.calls.filter(({ url }) => new URL(url).searchParams.has('page'))).toHaveLength(2);
  });

  it('renders an empty reward shop for a child', async () => {
    renderPage(buildUser(), [
      http.get('*/api/rewards/', () => HttpResponse.json([])),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 0, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getAllByText((t) => /coin|reward|bazaar|shop/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('renders parent reward shop with rewards + redemption queue', async () => {
    renderPage(buildParent(), [
      http.get('*/api/rewards/', () =>
        HttpResponse.json([{ id: 1, name: 'Ice Cream', cost: 50, stock: 5, rarity: 'common', image: '/ic.jpg' }]),
      ),
      http.get('*/api/redemptions/', () =>
        HttpResponse.json([{ id: 9, reward: { name: 'Toy', icon: '🧸' }, user_name: 'Abby', status: 'pending' }]),
      ),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 120, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
    ]);
    // Either the reward title (Ice Cream) or the redemption row (Toy) renders
    // depending on the active tab; assert at least one is visible.
    await waitFor(() =>
      expect(screen.getAllByText((t) => /ice cream|toy|abby/i.test(t)).length).toBeGreaterThan(0),
    );
  });

  it('filters the bazaar by name when the child types in the search', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/rewards/', () =>
        HttpResponse.json([
          { id: 1, name: 'Ice Cream', cost_coins: 50, rarity: 'common', is_active: true },
          { id: 2, name: 'Movie Night', cost_coins: 80, rarity: 'rare', is_active: true },
        ]),
      ),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 120, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText('Ice Cream')).toBeInTheDocument());

    const search = screen.getByRole('searchbox', { name: /filter rewards/i });
    await user.type(search, 'movie');

    expect(screen.queryByText('Ice Cream')).not.toBeInTheDocument();
    expect(screen.getByText('Movie Night')).toBeInTheDocument();
  });

  function redeemHandlers(redeem) {
    return [
      http.get('*/api/rewards/', () =>
        HttpResponse.json([{ id: 13, name: 'Ice Cream', cost_coins: 50, stock: 5, rarity: 'common', is_active: true }]),
      ),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 120, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/rate/', () => HttpResponse.json({ coins_per_dollar: 10 })),
      ...(redeem ? [redeem.handler] : []),
    ];
  }

  it('child confirming a reward request posts to /rewards/{id}/redeem/', async () => {
    const user = userEvent.setup();
    const redeem = spyHandler('post', /\/api\/rewards\/\d+\/redeem\/$/, { ok: true });
    renderPage(buildUser(), redeemHandlers(redeem));

    await user.click(await screen.findByRole('button', { name: /request reward/i }));

    // Coins are held on request with no kid-side undo, so the spend goes
    // through a confirm step showing the balance it will leave behind.
    const sheet = await screen.findByRole('dialog', { name: /ice cream/i });
    expect(within(sheet).getByText('120 → 70')).toBeInTheDocument();
    expect(redeem.calls).toHaveLength(0);

    await user.click(within(sheet).getByRole('button', { name: /request reward/i }));

    await waitFor(() => expect(redeem.calls).toHaveLength(1));
    expect(redeem.calls[0].url).toMatch(/\/rewards\/13\/redeem\/$/);
    expect(redeem.calls[0].body).toEqual({});
  });

  it('confirms a saved reward request using its actual held cost and opens its history', async () => {
    const user = userEvent.setup();
    const savedRequest = {
      id: 91, status: 'pending', coin_cost_snapshot: 60,
      reward: { id: 13, name: 'Ice Cream Sundae', icon: '🍨' },
      requested_at: '2026-10-14T12:00:00Z',
    };
    const redeem = spyHandler('post', '*/api/rewards/13/redeem/', savedRequest);
    renderPage(buildUser(), redeemHandlers(redeem));

    await user.click(await screen.findByRole('button', { name: /request reward/i }));
    const confirm = await screen.findByRole('dialog', { name: /ice cream/i });
    expect(screen.queryByRole('status', { name: 'Reward request update' })).not.toBeInTheDocument();
    await user.click(within(confirm).getByRole('button', { name: /request reward/i }));

    const receipt = await screen.findByRole('status', { name: 'Reward request update' });
    expect(receipt).toHaveTextContent('Request sent — awaiting parent approval');
    expect(receipt).toHaveTextContent('Ice Cream Sundae');
    expect(receipt).toHaveTextContent('60 coins held for this request');
    expect(receipt).not.toHaveTextContent('50 coins held');
    expect(redeem.calls).toHaveLength(1);
    expect(new URL(redeem.calls[0].url).pathname).toBe('/api/rewards/13/redeem/');
    expect(redeem.calls[0].body).toEqual({});

    await user.click(screen.getByRole('button', { name: 'View request history' }));
    const history = await screen.findByRole('dialog', { name: 'Reward request history' });
    expect(within(history).getByText('Ice Cream Sundae')).toBeInTheDocument();
    expect(within(history).getByText('pending')).toBeInTheDocument();
    expect(within(history).getByText(/60 coins/)).toBeInTheDocument();
    expect(redeem.calls).toHaveLength(1);
  });

  it('confirms an automatically fulfilled reward without saying parent approval is needed', async () => {
    const user = userEvent.setup();
    const redeem = spyHandler('post', '*/api/rewards/13/redeem/', {
      id: 92, status: 'fulfilled', coin_cost_snapshot: 45,
      reward: { id: 13, name: 'Ice Cream', icon: '🍨' },
      requested_at: '2026-10-14T12:00:00Z',
    });
    renderPage(buildUser(), redeemHandlers(redeem));
    await user.click(await screen.findByRole('button', { name: /request reward/i }));
    const confirm = await screen.findByRole('dialog', { name: /ice cream/i });
    await user.click(within(confirm).getByRole('button', { name: /request reward/i }));

    const receipt = await screen.findByRole('status', { name: 'Reward request update' });
    expect(receipt).toHaveTextContent('Reward received');
    expect(receipt).toHaveTextContent('45 coins spent');
    expect(receipt).not.toHaveTextContent('awaiting parent approval');
    expect(redeem.calls).toHaveLength(1);
    expect(redeem.calls[0].body).toEqual({});
  });

  it('keeps the saved receipt when refresh fails and retries reads without repeating the request', async () => {
    const user = userEvent.setup();
    let saved = false;
    let failRefresh = true;
    const savedRequest = {
      id: 93, status: 'pending', coin_cost_snapshot: 50,
      reward: { id: 13, name: 'Ice Cream', icon: '🍨' },
      requested_at: '2026-10-14T12:00:00Z',
    };
    const redeem = spyHandler('post', '*/api/rewards/13/redeem/', () => {
      saved = true;
      return savedRequest;
    });
    const historyReads = spyHandler('get', '*/api/redemptions/', () => {
      if (saved && failRefresh) return HttpResponse.json({ detail: 'History temporarily unavailable' }, { status: 503 });
      return saved ? [savedRequest] : [];
    });
    renderPage(buildUser(), [historyReads.handler, ...redeemHandlers(redeem)]);
    await user.click(await screen.findByRole('button', { name: /request reward/i }));
    const confirm = await screen.findByRole('dialog', { name: /ice cream/i });
    await user.click(within(confirm).getByRole('button', { name: /request reward/i }));

    expect(await screen.findByRole('status', { name: 'Reward request update' })).toHaveTextContent('Request sent — awaiting parent approval');
    expect(await screen.findByText(/Your request is saved. Some details couldn't refresh/)).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('History temporarily unavailable');
    failRefresh = false;
    await user.click(screen.getByRole('button', { name: 'Refresh reward details' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(screen.getByRole('status', { name: 'Reward request update' })).toHaveTextContent('50 coins held');
    await waitFor(() => expect(historyReads.calls).toHaveLength(3));
    expect(redeem.calls).toHaveLength(1);
    expect(redeem.calls[0].body).toEqual({});
  });

  it('shows a rejected request error without a saved receipt and allows an explicit retry', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const redeem = spyHandler('post', '*/api/rewards/13/redeem/', () => {
      attempts += 1;
      return attempts === 1
        ? HttpResponse.json({ detail: 'Request was not accepted' }, { status: 400 })
        : { id: 94, status: 'pending', coin_cost_snapshot: 50, reward: { id: 13, name: 'Ice Cream' } };
    });
    renderPage(buildUser(), redeemHandlers(redeem));
    await user.click(await screen.findByRole('button', { name: /request reward/i }));
    let confirm = await screen.findByRole('dialog', { name: /ice cream/i });
    await user.click(within(confirm).getByRole('button', { name: /request reward/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Request was not accepted');
    expect(screen.queryByRole('status', { name: 'Reward request update' })).not.toBeInTheDocument();
    expect(redeem.calls).toHaveLength(1);

    await user.click(screen.getByRole('button', { name: /request reward/i }));
    confirm = await screen.findByRole('dialog', { name: /ice cream/i });
    await user.click(within(confirm).getByRole('button', { name: /request reward/i }));
    expect(await screen.findByRole('status', { name: 'Reward request update' })).toHaveTextContent('Request sent — awaiting parent approval');
    expect(redeem.calls).toHaveLength(2);
    expect(redeem.calls.every(({ body }) => JSON.stringify(body) === '{}')).toBe(true);
  });

  it('backing out of the reward request confirm spends nothing', async () => {
    const user = userEvent.setup();
    const redeem = spyHandler('post', /\/api\/rewards\/\d+\/redeem\/$/, { ok: true });
    renderPage(buildUser(), redeemHandlers(redeem));

    await user.click(await screen.findByRole('button', { name: /request reward/i }));
    const sheet = await screen.findByRole('dialog', { name: /ice cream/i });
    await user.click(within(sheet).getByRole('button', { name: /cancel/i }));

    await waitFor(() =>
      expect(screen.queryByRole('dialog', { name: /ice cream/i })).not.toBeInTheDocument(),
    );
    expect(redeem.calls).toHaveLength(0);
  });

  it('parent approving a redemption posts to /redemptions/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/redemptions\/\d+\/approve\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/rewards/', () => HttpResponse.json([])),
      http.get('*/api/redemptions/', () =>
        HttpResponse.json([{ id: 22, reward: { name: 'Toy', icon: '🧸' }, user_name: 'Abby', status: 'pending', coin_cost_snapshot: 80, requested_at: '2026-04-15T12:00:00Z' }]),
      ),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 0, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/rate/', () => HttpResponse.json({ coins_per_dollar: 10 })),
      approve.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^approve$/i });
    await user.click(button);

    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/redemptions\/22\/approve\/$/);
    expect(approve.calls[0].body).toEqual({ notes: '' });
  });

  it('insufficient-coins disables requesting a reward and labels the button "Not enough coins"', async () => {
    // First-line signal: when balance < cost the button is disabled outright.
    // The "need N more" toast in Rewards.jsx is defense-in-depth for stale
    // balances, but the standard render path leans on the disabled button so
    // a kid never wastes a tap on a cost they can't pay.
    const redeem = spyHandler('post', /\/api\/rewards\/\d+\/redeem\/$/, { ok: true });
    renderPage(buildUser(), [
      http.get('*/api/rewards/', () =>
        HttpResponse.json([{
          id: 13,
          name: 'Ice Cream',
          cost: 50,
          cost_coins: 50,
          stock: 5,
          rarity: 'common',
          is_active: true,
        }]),
      ),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 38, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/rate/', () => HttpResponse.json({ coins_per_dollar: 10 })),
      redeem.handler,
    ]);

    const button = await screen.findByRole('button', { name: /not enough coin/i });
    expect(button).toBeDisabled();
    // No /redeem/ call ever fires — the button's disabled, the click is a no-op.
    expect(redeem.calls).toHaveLength(0);
  });

  it('wishlist toggle optimistically flips before the server responds', async () => {
    // The POST resolves after a delay so the test can assert that the
    // bookmark icon has ALREADY flipped to the "remove" aria-label state
    // while the network call is still in flight.
    const user = userEvent.setup();
    let resolveAdd;
    const addPromise = new Promise((r) => { resolveAdd = r; });
    server.use(
      http.get('*/api/rewards/', () =>
        HttpResponse.json([{
          id: 13, name: 'Ice Cream', cost_coins: 50, cost: 50, stock: 5,
          rarity: 'common', is_active: true, on_my_wishlist: false,
        }]),
      ),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 120, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/rate/', () => HttpResponse.json({ coins_per_dollar: 10 })),
      http.post(/\/api\/rewards\/13\/wishlist\/$/, async () => {
        await addPromise;
        return HttpResponse.json({ ok: true });
      }),
    );
    renderPage(buildUser(), []);

    const addBtn = await screen.findByRole('button', { name: /add ice cream to wishlist/i });
    await user.click(addBtn);

    // Optimistic: aria-label flips immediately while the POST is still
    // pending (resolveAdd hasn't been called).
    expect(await screen.findByRole('button', { name: /remove ice cream from wishlist/i }))
      .toBeInTheDocument();

    resolveAdd();
  });

  it('wishlist toggle rolls back when the server rejects', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/rewards/', () =>
        HttpResponse.json([{
          id: 13, name: 'Ice Cream', cost_coins: 50, cost: 50, stock: 5,
          rarity: 'common', is_active: true, on_my_wishlist: false,
        }]),
      ),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 120, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/rate/', () => HttpResponse.json({ coins_per_dollar: 10 })),
      http.post(/\/api\/rewards\/13\/wishlist\/$/, () =>
        HttpResponse.json({ detail: 'nope' }, { status: 500 }),
      ),
    );
    renderPage(buildUser(), []);

    const addBtn = await screen.findByRole('button', { name: /add ice cream to wishlist/i });
    await user.click(addBtn);

    // Optimistic flip happened, then the failure rolled it back to "add".
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /add ice cream to wishlist/i }))
        .toBeInTheDocument(),
    );
  });

  it('a failed balance fetch shows a retry-able alert instead of a gold "0"', async () => {
    const user = userEvent.setup();
    let attempts = 0;
    renderPage(buildUser(), [
      http.get('*/api/rewards/', () => HttpResponse.json([])),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => {
        attempts += 1;
        if (attempts === 1) return HttpResponse.json({ detail: 'boom' }, { status: 500 });
        return HttpResponse.json({ balance: 42, recent: [] });
      }),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/rate/', () => HttpResponse.json({ coins_per_dollar: 10 })),
    ]);

    await waitFor(() =>
      expect(screen.getByText(/couldn't load your coin balance/i)).toBeInTheDocument(),
    );
    // The false zero is gone — no balance is claimed at all.
    expect(screen.queryByText('0')).toBeNull();

    await user.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() => expect(screen.getByText('42')).toBeInTheDocument());
  });

  it('a failed rewards fetch shows a retry-able alert instead of "no rewards yet"', async () => {
    renderPage(buildUser(), [
      http.get('*/api/rewards/', () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 10, recent: [] })),
      http.get('*/api/coins/exchange/list/', () => HttpResponse.json([])),
      http.get('*/api/coins/exchange/rate/', () => HttpResponse.json({ coins_per_dollar: 10 })),
    ]);

    await waitFor(() =>
      expect(screen.getByText(/couldn't load the reward shop/i)).toBeInTheDocument(),
    );
    expect(screen.queryByText(/ask a parent to add one/i)).toBeNull();
  });

  it('parent approving an exchange posts to /coins/exchange/{id}/approve/', async () => {
    const user = userEvent.setup();
    const approve = spyHandler('post', /\/api\/coins\/exchange\/\d+\/approve\/$/, { ok: true });
    renderPage(buildParent(), [
      http.get('*/api/rewards/', () => HttpResponse.json([])),
      http.get('*/api/redemptions/', () => HttpResponse.json([])),
      http.get('*/api/coins/', () => HttpResponse.json({ balance: 0, recent: [] })),
      http.get('*/api/coins/exchange/list/', () =>
        HttpResponse.json([{ id: 33, user_name: 'Abby', dollar_amount: '2.00', coin_amount: 20, exchange_rate: 10, status: 'pending', created_at: '2026-04-15T12:00:00Z' }]),
      ),
      http.get('*/api/coins/exchange/rate/', () => HttpResponse.json({ coins_per_dollar: 10 })),
      approve.handler,
    ]);

    const button = await screen.findByRole('button', { name: /^approve$/i });
    await user.click(button);

    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(approve.calls[0].url).toMatch(/\/coins\/exchange\/33\/approve\/$/);
    expect(approve.calls[0].body).toEqual({ notes: '' });
  });
});
