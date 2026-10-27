import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import dashboard from '../../../contracts/api/fixtures/parent-family-overview.json';
import ParentFamilyOverview from '../pages/dashboard/ParentFamilyOverview';
import { server } from '../test/server';
import { getDashboard } from './index';
import { getAwaitingRedemptions, deliverRedemption } from './index';
import approvedReward from '../../../contracts/api/fixtures/parent-reward-approved.json';
import deliveredReward from '../../../contracts/api/fixtures/parent-reward-delivered.json';
import inactiveDeliveredReward from '../../../contracts/api/fixtures/parent-reward-inactive-delivered.json';
import RewardDeliveryQueue from '../pages/rewards/RewardDeliveryQueue';
import userEvent from '@testing-library/user-event';
import { spyHandler } from '../test/spy';
import personalDashboard from '../../../contracts/api/fixtures/parent-personal-dashboard.json';
import childOverview from '../../../contracts/api/fixtures/family-child-overview.json';
import { getChildOverview } from './index';
import { setRequestSpace } from './space';
import { getToken } from './client';

describe('parent dashboard response through the real React API client', () => {
  it('reads personal progression with the original parent identity', async () => {
    let hint;
    server.use(http.get('*/api/dashboard/', ({ request }) => {
      hint = request.headers.get('X-Abby-Space'); return HttpResponse.json(personalDashboard);
    }));
    setRequestSpace('personal', getToken());
    try {
      const data = await getDashboard();
      expect(hint).toBe('personal');
      expect(data.role).toBe('parent');
      expect(data.coin_balance).toBe(35);
      expect(data.next_actions.map(row => row.title)).toEqual(['Read after breakfast']);
      expect(data).not.toHaveProperty('family_overview');
    } finally { setRequestSpace('family', getToken()); }
  });

  it('reads a child’s saved overview in Family even while My space is selected', async () => {
    let hint;
    server.use(http.get('*/api/children/7/overview/', ({ request }) => {
      hint = request.headers.get('X-Abby-Space'); return HttpResponse.json(childOverview);
    }));
    setRequestSpace('personal', getToken());
    try {
      const data = await getChildOverview(7);
      expect(hint).toBeNull();
      expect(data.child).toEqual({ id: 7, display_name: 'Abby' });
      expect(data.coin_balance).toBe(45);
      expect(data.skills[0]).toMatchObject({ skill_name: 'Drawing', xp_points: 25 });
      expect(data.badges[0].badge.name).toBe('First drawing');
      expect(data).not.toHaveProperty('journals');
    } finally { setRequestSpace('family', getToken()); }
  });
  it('retains the saved inactive-child handover audit on delivery replay', async () => {
    const delivery = spyHandler('post', '*/api/redemptions/902/deliver/', inactiveDeliveredReward);
    server.use(delivery.handler);
    const delivered = await deliverRedemption(inactiveDeliveredReward.id);
    expect(delivered).toEqual(inactiveDeliveredReward);
    expect(delivered.status).toBe('fulfilled');
    expect(delivered.delivered_by).toBe(6);
    expect(delivered.delivered_at).toBeTruthy();
    expect(delivered.decided_at).toBeTruthy();
    expect(await deliverRedemption(inactiveDeliveredReward.id)).toEqual(delivered);
    expect(delivery.calls.map((call) => call.body)).toEqual([{}, {}]);
  });

  it('uses the saved approval and delivery receipts for a real-world reward', async () => {
    const user = userEvent.setup();
    const delivery = spyHandler('post', '*/api/redemptions/902/deliver/', deliveredReward);
    server.use(http.get('*/api/redemptions/', () => HttpResponse.json({ count: 1, next: null, results: [approvedReward] })), delivery.handler);
    const rewards = await getAwaitingRedemptions();
    expect(rewards[0].status).toBe('approved');
    render(<RewardDeliveryQueue rewards={rewards} onDeliver={async (id) => {
      const receipt = await deliverRedemption(id);
      expect(receipt).toEqual(deliveredReward);
      expect(receipt.delivered_by).toBe(6);
      expect(receipt.decided_at).toBe(approvedReward.decided_at);
    }} />);
    await user.click(screen.getByRole('button', { name: 'Mark delivered' }));
    await user.click(screen.getByRole('button', { name: 'Confirm delivered' }));
    expect(delivery.calls).toHaveLength(1);
    expect(delivery.calls[0].body).toEqual({});
  });
  it('renders the household work and accomplishments without private source content', async () => {
    server.use(http.get('*/api/dashboard/', () => HttpResponse.json(dashboard)));
    const body = await getDashboard();
    expect(body).toEqual(dashboard);
    render(
      <MemoryRouter>
        <ParentFamilyOverview overview={body.family_overview} children={[]} weekByKid={[]} loading={false} unavailable={false} />
      </MemoryRouter>,
    );
    expect(body.family_overview.date).toBe('2026-10-18');
    const abby = screen.getByRole('heading', { name: 'Abby' }).closest('article');
    expect(within(abby).getByText('1 due today · 1 overdue')).toBeVisible();
    expect(within(abby).getByText('1 awaiting your review')).toBeVisible();
    expect(within(abby).getByText('1 remaining · 0 awaiting review · 1 approved')).toBeVisible();
    expect(within(abby).getByText('7.5 / 20 minutes')).toBeVisible();
    expect(within(abby).getByText('Earned a badge: Steady learner')).toBeVisible();
    expect(within(abby).getByRole('link', { name: "View Abby's homework" })).toHaveAttribute('href', '/quests?tab=study&child=7');
    expect(within(abby).getByText(/1.5h clocked · \$15.00 clocked earnings/)).toBeVisible();
    const ben = screen.getByRole('heading', { name: 'Ben' }).closest('article');
    expect(within(ben).getByText('No active parent goals.')).toBeVisible();
    expect(within(ben).getByText('New accomplishments will appear here.')).toBeVisible();
    expect(screen.queryByText(/private|other family's/i)).not.toBeInTheDocument();
  });
});
