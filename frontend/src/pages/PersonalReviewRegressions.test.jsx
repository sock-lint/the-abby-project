import { beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, waitFor, within } from '../test/render';
import { server } from '../test/server';
import { buildParent, buildProject } from '../test/factories';
import { buildChallengeGoal, buildDailyBonus } from '../test/challenges';
import { spyHandler } from '../test/spy';
import { SpaceContext } from '../providers/spaceContext';
import DailyChallengeCard from '../components/dashboard/DailyChallengeCard';
import QuickActionsSheet from '../components/layout/QuickActionsSheet';
import QuestProgressToastStack from '../components/QuestProgressToastStack';
import FirstEncounterSheet from '../components/lorebook/FirstEncounterSheet';
import ApprovalToastStack from '../components/ApprovalToastStack';
import NotificationBell from '../components/NotificationBell';
import { notificationSpace } from '../components/notifications.constants';
import { useAuth } from '../hooks/useApi';
import ProjectDetail from './ProjectDetail';
import Trials from './trials';
import Chores from './Chores';
import ClockPage from './ClockPage';
import { emptyPulse } from '../test/pulseFixtures';

vi.mock('framer-motion', async importOriginal => ({
  ...await importOriginal(), AnimatePresence: ({ children }) => children,
}));
const parent = buildParent({ id: 90 });
const personal = { space: 'personal', isPersonalSpace: true, isFamilySpace: false, isParentAccount: true };
const family = { ...personal, space: 'family', isPersonalSpace: false, isFamilySpace: true };
function renderSpace(ui, { space = personal, ...options } = {}) {
  return renderWithProviders(<SpaceContext.Provider value={space}>{ui}</SpaceContext.Provider>, options);
}
function AccountProbe() {
  const { user } = useAuth();
  return <output aria-label="Account role">{user?.role}</output>;
}
beforeEach(() => server.use(http.get('*/api/auth/me/', () => HttpResponse.json(parent))));

describe('Parent personal participation review regressions', () => {
  it('shows a parent their confirmed daily bonus in My space', async () => {
    renderSpace(<DailyChallengeCard challenge={buildDailyBonus({ awarded: true, completed: true, receipt_id: 'daily:90', coins_awarded: 10, xp_awarded: 20 })} />);
    expect(await screen.findByRole('heading', { name: "Today's bonus" })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Bonus earned · +10 coins · +20 XP');
  });

  it('keeps Family free of a parent personal bonus', async () => {
    renderSpace(<DailyChallengeCard challenge={buildDailyBonus()} />, { space: family });
    await waitFor(() => expect(screen.queryByRole('heading', { name: "Today's bonus" })).not.toBeInTheDocument());
  });

  it('records a parent opening their catalog challenge and confirms the server timestamp', async () => {
    const goal = buildChallengeGoal({ id: 'goal:31', origin: 'catalog', catalog_repeatable: false, first_details_opened_at: null });
    const opening = spyHandler('post', /\/api\/challenges\/goal(?::|%3A)31\/opened\/$/, { id: goal.id, first_details_opened_at: '2026-10-27T12:00:00Z' });
    server.use(opening.handler, http.get('*/api/challenges/', () => HttpResponse.json({ results: [goal], pin: null, daily_bonus: null })));
    renderSpace(<Trials />, { route: '/quests?tab=trials&goal=goal:31' });
    await screen.findByRole('dialog');
    await waitFor(() => expect(opening.calls).toHaveLength(1));
  });

  it('shows a parent their personal challenge receipt', async () => {
    renderSpace(<QuestProgressToastStack />, { pulse: emptyPulse({ challenge_receipts: [{
      id: 'activity:90', goals: [{ id: 'goal:31', name: 'My completed goal', progress: '2', target: '2', unit: 'actions', completed: true, rewards: { coins: 10, xp: 20, items: [] } }], daily_bonus: null,
    }] }) });
    expect(await screen.findByText('My completed goal')).toBeInTheDocument();
    expect(screen.getByRole('listitem')).toHaveTextContent('Completed · +10 coins · +20 XP');
  });

  it('keeps personal project and milestone views free of cash reward promises', async () => {
    const project = buildProject({ assigned_to: parent, bonus_amount: '40.00', hourly_rate_override: '8.00', materials_budget: '25.00', milestones: [{ id: 3, title: 'Build the base', bonus_amount: '18.00' }] });
    server.use(http.get('*/api/projects/1/', () => HttpResponse.json(project)));
    const { user } = renderSpace(<ProjectDetail />, { route: '/quests/ventures/1', routePath: '/quests/ventures/:id' });
    await screen.findByRole('tab', { name: 'Plan' });
    expect(screen.queryByText('Bonus')).not.toBeInTheDocument();
    expect(screen.queryByText('$40.00')).not.toBeInTheDocument();
    expect(screen.queryByText(/rate override/)).not.toBeInTheDocument();
    expect(screen.getByText('$25.00')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Plan' }));
    expect(await screen.findByText('Build the base')).toBeInTheDocument();
    expect(screen.queryByText('18.00')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Mark milestone complete' }));
    const confirm = await screen.findByRole('alertdialog', { name: 'Mark this milestone complete?' });
    expect(confirm).not.toHaveTextContent('pay the $18.00 bonus');
  });

  it('completes a parent’s own Family project with parent controls and retains Family authoring', async () => {
    const project = buildProject({ status: 'in_progress', assigned_to: parent, bonus_amount: '40.00', materials_budget: '25.00' });
    const approve = spyHandler('post', /\/api\/projects\/1\/approve\/$/, { ...project, status: 'completed' });
    const submit = spyHandler('post', /\/api\/projects\/1\/submit\/$/, { ...project, status: 'in_review' });
    server.use(approve.handler, submit.handler, http.get('*/api/projects/1/', () => HttpResponse.json(project)));
    const { user } = renderSpace(<><AccountProbe /><ProjectDetail /></>, { space: family, route: '/quests/ventures/1', routePath: '/quests/ventures/:id' });
    await user.click(await screen.findByRole('button', { name: 'Complete project' }));
    await waitFor(() => expect(approve.calls).toHaveLength(1));
    expect(submit.calls).toHaveLength(0);
    expect(screen.getByRole('status', { name: 'Account role' })).toHaveTextContent('parent');
    expect(await screen.findByRole('button', { name: 'Edit' })).toBeInTheDocument();
    expect(screen.getByText('$40.00')).toBeInTheDocument();
  });

  it('offers parent personal authoring actions without child approval wording or the unavailable print tab', async () => {
    renderSpace(<QuickActionsSheet status={{}} isClocked={false} elapsedSecs={0} onClose={vi.fn()} onClockReload={vi.fn()} />);
    const sheet = await screen.findByRole('dialog', { name: 'Quick actions' });
    expect(within(sheet).getByRole('button', { name: /New chore/ })).toBeInTheDocument();
    expect(within(sheet).getByRole('button', { name: /New habit/ })).toBeInTheDocument();
    expect(within(sheet).queryByRole('button', { name: /Ask for a print/ })).not.toBeInTheDocument();
    expect(within(sheet).queryByText(/parent sets/)).not.toBeInTheDocument();
  });

  it('offers parent personal guide encounters and saves their own seen flag', async () => {
    const save = spyHandler('patch', /\/api\/auth\/me\/$/, { ...parent, lorebook_flags: { first_habit_seen: true } });
    server.use(save.handler, http.get('*/api/lorebook/', () => HttpResponse.json({ entries: [{ slug: 'first_habit', title: 'Your first habit' }] })));
    const { user } = renderSpace(<FirstEncounterSheet />, { pulse: emptyPulse({ newly_unlocked_lorebook: ['first_habit'] }) });
    const sheet = await screen.findByRole('dialog', { name: 'New guide available' });
    await user.click(within(sheet).getByRole('button', { name: 'Later' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toMatchObject({ lorebook_flags: { first_habit_seen: true } });
  });

  it('shows a parent a new decision about their own personal submission', async () => {
    const { beat } = renderSpace(<><AccountProbe /><ApprovalToastStack /></>, { pulse: emptyPulse() });
    await waitFor(() => expect(screen.getByRole('status', { name: 'Account role' })).toHaveTextContent('parent'));
    beat(emptyPulse({ notifications: [{ id: 123, notification_type: 'creation_approved', title: 'Your own creation was approved', message: 'Saved in your gallery' }] }));
    expect(await screen.findByText('Your own creation was approved')).toBeInTheDocument();
  });

  it('keeps an inactive personal chore identifiable and editable', async () => {
    const update = spyHandler('patch', /\/api\/chores\/7\/$/, { id: 7, is_active: true });
    server.use(update.handler, http.get('*/api/chores/', ({ request }) => HttpResponse.json(new URL(request.url).searchParams.has('pending') ? [] : [{ id: 7, title: 'Pause my practice', assigned_to: parent.id, is_active: false, is_available: false, recurrence: 'daily', reward_amount: '0.00', coin_reward: 5 }])), http.get('*/api/chore-completions/', () => HttpResponse.json([])));
    const { user } = renderSpace(<Chores />);
    expect(await screen.findByText('Pause my practice')).toBeInTheDocument();
    expect(screen.getByText('inactive')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Done' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Edit chore' }));
    const form = await screen.findByRole('dialog', { name: 'Edit chore' });
    await user.click(within(form).getByRole('checkbox', { name: 'Active' }));
    await user.click(within(form).getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].body).toMatchObject({ assigned_to: parent.id, is_active: true, reward_amount: '0.00' });
  });

  it('shows personal chore rewards as Coins without a cash promise', async () => {
    server.use(http.get('*/api/chores/', ({ request }) => HttpResponse.json(new URL(request.url).searchParams.has('pending') ? [] : [{ id: 7, title: 'My practice', assigned_to: parent.id, is_active: true, is_available: true, recurrence: 'daily', reward_amount: '0.00', coin_reward: 5 }])), http.get('*/api/chore-completions/', () => HttpResponse.json([{ id: 8, chore_title: 'Yesterday’s practice', chore_icon: '📋', status: 'approved', reward_amount_snapshot: '0.00', coin_reward_snapshot: 5 }])));
    const { container } = renderSpace(<Chores />);
    expect(await screen.findByText('Yesterday’s practice')).toBeInTheDocument();
    expect(container).not.toHaveTextContent('$0.00');
    expect(container.querySelector('.lucide-dollar-sign')).toBeNull();
  });

  it('describes parent personal time as progression without weekly pay', async () => {
    renderSpace(<ClockPage />);
    expect(await screen.findByText('Log project time to earn coins and XP.')).toBeInTheDocument();
    expect(screen.queryByText(/weekly pay/)).not.toBeInTheDocument();
  });

  it('lets a parent save their own active session without directing them to Family timecards', async () => {
    server.use(http.get('*/api/clock/', () => HttpResponse.json({ status: 'active', project_title: 'My ongoing project', clock_in: new Date(Date.now() - 300_000).toISOString() })));
    const { user } = renderSpace(<ClockPage />);
    expect(await screen.findByText('Clock out to save this project session.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clock out' }));
    const confirm = await screen.findByRole('alertdialog');
    expect(within(confirm).getByText('This saves your project session. You can void the entry afterward if needed.')).toBeInTheDocument();
    expect(within(confirm).queryByText(/weekly timecard/)).not.toBeInTheDocument();
  });

  it.each(['homework_created', 'print_request_approved', 'print_request_rejected', 'print_started', 'print_finished', 'print_failed'])('opens %s in Family', notification_type => {
    expect(notificationSpace({ notification_type })).toBe('family');
  });

  it('uses the explicit child Family destination for a pet notification instead of the parent’s pets', async () => {
    const switchSpace = vi.fn();
    const { user } = renderSpace(<NotificationBell />, { space: { ...personal, switchSpace }, pulse: emptyPulse({ notifications: [{ id: 18, is_read: true, notification_type: 'pet_evolved', title: 'Your child’s pet evolved', link: '/family?child=7' }] }) });
    await user.click(await screen.findByRole('button', { name: 'Notifications' }));
    await user.click(await screen.findByRole('button', { name: 'Your child’s pet evolved' }));
    expect(switchSpace).toHaveBeenCalledExactlyOnceWith('family', '/family?child=7');
  });

  it.each(['pet_evolved', 'expedition_returned'])('opens a parent’s ambiguous legacy pet notification in the generic Children overview: %s', async (notification_type) => {
    const switchSpace = vi.fn();
    const { user } = renderSpace(<NotificationBell />, { space: { ...personal, switchSpace }, pulse: emptyPulse({ notifications: [{ id: 19, is_read: true, notification_type, title: 'Earlier pet update', link: '/bestiary?tab=mounts' }] }) });
    await user.click(await screen.findByRole('button', { name: 'Notifications' }));
    await user.click(await screen.findByRole('button', { name: 'Earlier pet update' }));
    expect(switchSpace).toHaveBeenCalledExactlyOnceWith('family', '/family');
  });

  it.each(['pet_evolved', 'expedition_returned'])('opens a parent’s explicit personal pet notification in My space: %s', async (notification_type) => {
    const switchSpace = vi.fn();
    const link = '/bestiary?tab=mounts&space=personal';
    const { user } = renderSpace(<NotificationBell />, { space: { ...family, switchSpace }, pulse: emptyPulse({ notifications: [{ id: 20, is_read: true, notification_type, title: 'Your pet update', link }] }) });
    await user.click(await screen.findByRole('button', { name: 'Notifications' }));
    await user.click(await screen.findByRole('button', { name: 'Your pet update' }));
    expect(switchSpace).toHaveBeenCalledExactlyOnceWith('personal', link);
  });
});
