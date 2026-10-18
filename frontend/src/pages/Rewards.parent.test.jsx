import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Rewards from './Rewards';
import { AuthProvider } from '../hooks/useApi';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildParent, buildUser } from '../test/factories';
import { selectDropdown } from '../test/selectDropdown';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const delivery = {
  id: 41, user: 7, user_name: 'Abby', status: 'approved', coin_cost_snapshot: 30,
  reward: { id: 2, name: 'Museum trip', fulfillment_kind: 'both', icon: '🎁' },
  decided_at: '2026-10-16T18:00:00Z', parent_notes: 'Saturday after lunch.',
};
function renderRewards(extra = [], account = buildParent()) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(account)),
    http.get('*/api/children/', () => HttpResponse.json([{ id: 7, display_name: 'Abby' }, { id: 8, display_name: 'Ben' }])),
    http.get('*/api/redemptions/', ({ request }) => HttpResponse.json(new URL(request.url).searchParams.get('status') === 'approved' ? [delivery] : [])),
  );
  server.use(...extra);
  return render(<MemoryRouter><AuthProvider><Rewards /></AuthProvider></MemoryRouter>);
}

describe('Parent reward oversight', () => {
  it('names the verified selected child wallet and never requests the parent wallet', async () => {
    const user = userEvent.setup();
    const coins = spyHandler('get', '*/api/coins/', ({ request }) => ({ balance: new URL(request.url).searchParams.get('user_id') === '7' ? 75 : 12 }));
    renderRewards([coins.handler]);
    expect(await screen.findByText("Abby's coin balance")).toBeInTheDocument();
    expect(await screen.findByText('75')).toBeInTheDocument();
    await selectDropdown(user, screen.getByLabelText('Viewing'), '8');
    expect(await screen.findByText("Ben's coin balance")).toBeInTheDocument();
    expect(await screen.findByText('12')).toBeInTheDocument();
    expect(screen.queryByText('75')).not.toBeInTheDocument();
    expect(coins.calls.map(({ url }) => new URL(url).searchParams.get('user_id'))).toEqual(['7', '8']);
  });

  it('fences an older child wallet read when the selected child changes', async () => {
    const user = userEvent.setup();
    let release;
    const oldRead = new Promise((resolve) => { release = resolve; });
    renderRewards([http.get('*/api/coins/', async ({ request }) => {
      if (new URL(request.url).searchParams.get('user_id') === '7') {
        await oldRead;
        return HttpResponse.json({ balance: 777 });
      }
      return HttpResponse.json({ balance: 12 });
    })]);
    await selectDropdown(user, await screen.findByLabelText('Viewing'), '8');
    expect(await screen.findByText('12')).toBeInTheDocument();
    await act(async () => { release(); await oldRead; });
    expect(screen.queryByText('777')).not.toBeInTheDocument();
    expect(screen.getByText("Ben's coin balance")).toBeInTheDocument();
  });

  it('defaults a manual coin adjustment to the selected child', async () => {
    const user = userEvent.setup();
    const adjust = spyHandler('post', '*/api/coins/adjust/', { ok: true });
    renderRewards([adjust.handler]);
    await selectDropdown(user, await screen.findByLabelText('Viewing'), '8');
    await user.click(screen.getByRole('button', { name: 'Adjust coins' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Adjust coins' }));
    await waitFor(() => expect(dialog.getByLabelText('Kid')).toHaveValue('8'));
    await user.type(dialog.getByLabelText('Amount (positive to add, negative to deduct)'), '5');
    await user.click(dialog.getByRole('button', { name: 'Adjust' }));
    await waitFor(() => expect(adjust.calls).toHaveLength(1));
    expect(adjust.calls[0].body).toEqual({ user_id: 8, amount: 5, description: '' });
    expect(adjust.calls[0].url).toMatch(/\/api\/coins\/adjust\/$/);
  });

  it('confirms real-world handover separately and keeps the confirmed receipt after a refresh fails', async () => {
    const user = userEvent.setup();
    let delivered = false;
    const post = spyHandler('post', '*/api/redemptions/41/deliver/', () => {
      delivered = true;
      return { ...delivery, status: 'fulfilled', delivered_at: '2026-10-17T19:00:00Z', delivered_by: 1 };
    });
    renderRewards([
      post.handler,
      http.get('*/api/redemptions/', ({ request }) => delivered
        ? HttpResponse.json({ detail: 'Could not refresh' }, { status: 503 })
        : HttpResponse.json(new URL(request.url).searchParams.get('status') === 'approved' ? [delivery] : [])),
    ]);
    const queue = within(await screen.findByRole('region', { name: 'Awaiting reward delivery' }));
    expect(await queue.findByText('Digital item already delivered. Real-world reward still to deliver.')).toBeInTheDocument();
    await user.click(queue.getByRole('button', { name: 'Mark delivered' }));
    const dialog = within(await screen.findByRole('dialog', { name: 'Confirm reward delivery' }));
    expect(post.calls).toHaveLength(0);
    await user.dblClick(dialog.getByRole('button', { name: 'Confirm delivered' }));
    await waitFor(() => expect(post.calls).toHaveLength(1));
    expect(post.calls[0].url).toMatch(/\/api\/redemptions\/41\/deliver\/$/);
    expect(post.calls[0].body).toEqual({});
    expect(await screen.findByText('Delivery confirmed for Museum trip.')).toBeInTheDocument();
    expect(await screen.findByText(/Couldn't load rewards awaiting delivery/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark delivered' })).not.toBeInTheDocument();
  });

  it('does not expose handover controls to a child', async () => {
    renderRewards([], buildUser());
    expect(await screen.findByRole('heading', { name: 'Rewards' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Awaiting reward delivery' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark delivered' })).not.toBeInTheDocument();
  });
});
