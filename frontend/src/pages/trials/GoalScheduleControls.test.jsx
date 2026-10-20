import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, within, waitFor, act } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { buildParent, buildUser } from '../../test/factories';
import { buildChallengeGoal } from '../../test/challenges';
import GoalScheduleControls from './GoalScheduleControls';
import { useRole } from '../../hooks/useRole';

const NEXT = { starts_at: '2026-10-26T07:00:00Z', paused: false, name: 'Weekly running', description: 'Make time to move.', metric: 'distance', target: '2', unit: 'mi', trigger_type: 'movement_session', movement_type_id: 3, coin_reward: 10, xp_reward: 0, skill_tags: [] };
function goalWithSchedule(overrides = {}) {
  return buildChallengeGoal({ goal_definition_id: 21, repeat_weekly: true, timezone: 'America/Phoenix', schedule: { revision: 0, paused: false, next_week: NEXT }, ...overrides });
}
function AuthState() { const { role } = useRole(); return role && <span>Role: {role}</span>; }
function setup({ goal = goalWithSchedule(), role = 'parent', onChanged = vi.fn(), onReload = vi.fn() } = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(role === 'parent' ? buildParent() : buildUser())),
    http.get('*/api/skills/', () => HttpResponse.json([{ id: 12, name: 'Persistence' }])),
  );
  return { ...renderWithProviders(<><GoalScheduleControls goal={goal} onChanged={onChanged} onReload={onReload} /><AuthState /></>), onChanged, onReload };
}
async function edit(user) {
  await user.click(await screen.findByRole('button', { name: 'Change future weeks' }));
  return screen.getByRole('dialog', { name: 'Change future weeks' });
}

describe('Parent future weekly goal controls', () => {
  it.each([false, true])('blocks pause and resume until current settings reload, including a concurrent refresh (%s)', async (concurrentRefresh) => {
    const current = goalWithSchedule({ schedule: { revision: 2, paused: false, next_week: { ...NEXT, paused: true } } });
    const onReload = vi.fn().mockResolvedValueOnce(undefined).mockResolvedValueOnce({ results: [current] });
    const conflict = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, () => HttpResponse.json({ error: 'Saved revision changed.' }, { status: 409 }));
    server.use(conflict.handler);
    function ChangingGoal() {
      const [goal, setGoal] = useState(goalWithSchedule());
      return <GoalScheduleControls goal={goal} onReload={async () => {
        const response = await onReload();
        if (concurrentRefresh && !response) setGoal(current);
        return response;
      }} />;
    }
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
    const { user } = renderWithProviders(<ChangingGoal />);
    const pause = await screen.findByRole('button', { name: 'Pause future weeks' });
    await user.click(pause);
    const retry = await screen.findByRole('button', { name: 'Retry saved future settings' });
    expect(pause).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Change future weeks' })).toBeDisabled();
    await user.click(pause);
    expect(conflict.calls).toHaveLength(1);
    await user.click(retry);
    const resume = await screen.findByRole('button', { name: 'Resume future weeks' });
    await waitFor(() => expect(resume).toBeEnabled());
    const save = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, { goal_definition_id: 21, schedule: { ...current.schedule, revision: 3, next_week: NEXT } });
    server.use(save.handler);
    await user.click(resume);
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body).toEqual({ expected_revision: 2, paused: false });
    expect(onReload).toHaveBeenCalledTimes(2);
  });

  it.each(['unchanged revision', 'other goal', 'missing schedule'])('keeps the draft blocked when a reload returns %s', async (shape) => {
    const current = goalWithSchedule({ schedule: { revision: 2, paused: false, next_week: NEXT } });
    const response = shape === 'unchanged revision' ? { results: [goalWithSchedule()] }
      : shape === 'other goal' ? { results: [{ ...current, goal_definition_id: 99 }] }
        : { results: [{ ...current, schedule: null }] };
    const onReload = vi.fn().mockResolvedValue(response);
    const conflict = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, () => HttpResponse.json({ error: 'Saved revision changed.' }, { status: 409 }));
    server.use(conflict.handler);
    const { user } = setup({ onReload });
    const dialog = await edit(user);
    const target = within(dialog).getByLabelText('Future target (miles)');
    await user.clear(target); await user.type(target, '3');
    await user.click(within(dialog).getByRole('button', { name: 'Save future weeks' }));
    await within(dialog).findByRole('button', { name: 'Retry saved future settings' });
    expect(within(dialog).getByRole('button', { name: 'Load saved future settings' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Save future weeks' })).toBeDisabled();
    expect(target).toHaveValue(3);
    expect(onReload).toHaveBeenCalledOnce();
    expect(conflict.calls).toHaveLength(1);
  });

  it('saves only the six future settings with the exact revision and a captured credential', async () => {
    let authorization;
    const save = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, ({ request }) => {
      authorization = request.headers.get('Authorization');
      return { goal_definition_id: 21, schedule: { revision: 1, paused: false, next_week: { ...NEXT, target: '3.5', coin_reward: 15 } } };
    });
    server.use(save.handler);
    const { user, onChanged } = setup();
    const dialog = await edit(user);
    expect(within(dialog).getByText(/These settings apply from Oct 26, 2026/)).toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText('Future target (miles)'));
    await user.type(within(dialog).getByLabelText('Future target (miles)'), '3.5');
    await user.clear(within(dialog).getByLabelText('Future Coin bonus'));
    await user.type(within(dialog).getByLabelText('Future Coin bonus'), '15');
    await user.click(within(dialog).getByRole('button', { name: 'Save future weeks' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0]).toEqual({ url: expect.stringMatching(/\/api\/challenges\/goals\/21\/schedule\/$/), method: 'PATCH', body: { expected_revision: 0, next_week: { name: NEXT.name, description: NEXT.description, target: '3.5', coin_reward: 15, xp_reward: 0, skill_tags: [] } } });
    expect(authorization).toBe('Token test-session');
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('resumes future weeks with the current saved revision', async () => {
    const resume = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, { goal_definition_id: 21, schedule: { revision: 4, paused: true, next_week: NEXT } });
    server.use(resume.handler);
    const { user, onChanged } = setup({ goal: goalWithSchedule({ schedule: { revision: 3, paused: true, next_week: { ...NEXT, paused: true } } }) });
    await user.click(await screen.findByRole('button', { name: 'Resume future weeks' }));
    await waitFor(() => expect(resume.calls).toHaveLength(1));
    expect(resume.calls[0].body).toEqual({ expected_revision: 3, paused: false });
    await waitFor(() => expect(onChanged).toHaveBeenCalledOnce());
  });

  it('keeps server field errors with the draft and never retries a rejected save', async () => {
    const save = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, () => HttpResponse.json({ next_week: { target: ['Choose a valid target.'] } }, { status: 400 }));
    server.use(save.handler);
    const { user } = setup();
    const dialog = await edit(user);
    await user.clear(within(dialog).getByLabelText('Future goal title'));
    await user.type(within(dialog).getByLabelText('Future goal title'), 'Next week plan');
    await user.click(within(dialog).getByRole('button', { name: 'Save future weeks' }));
    expect(await within(dialog).findByText('Choose a valid target.')).toHaveAttribute('role', 'alert');
    expect(within(dialog).getByLabelText('Future target (miles)')).toHaveAttribute('aria-invalid', 'true');
    expect(within(dialog).getByLabelText('Future goal title')).toHaveValue('Next week plan');
    expect(save.calls).toHaveLength(1);
  });

  it('requires an XP skill and recovers unavailable skills through an explicit retry', async () => {
    const save = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, { goal_definition_id: 21, schedule: { revision: 1, paused: false, next_week: NEXT } });
    server.use(save.handler);
    const { user } = setup();
    // Override setup's successful picker response before it is opened.
    server.use(http.get('*/api/skills/', () => HttpResponse.json({ error: 'Skills unavailable.' }, { status: 503 })));
    const dialog = await edit(user);
    await user.clear(within(dialog).getByLabelText('Future XP bonus'));
    await user.type(within(dialog).getByLabelText('Future XP bonus'), '20');
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Skills unavailable.');
    expect(within(dialog).getByRole('button', { name: 'Save future weeks' })).toBeDisabled();
    const skills = spyHandler('get', /\/api\/skills\/$/, [{ id: 12, name: 'Persistence' }]);
    server.use(skills.handler);
    await user.click(within(dialog).getByRole('button', { name: 'Retry skills' }));
    await within(dialog).findByRole('button', { name: 'Add skill' });
    await user.click(within(dialog).getByRole('button', { name: 'Save future weeks' }));
    const group = within(dialog).getByRole('group', { name: 'Skills this rewards' });
    expect(group).toHaveAccessibleDescription('Choose a skill to receive the XP bonus.');
    expect(save.calls).toHaveLength(0);
    await user.click(within(group).getByRole('button', { name: 'Add skill' }));
    await user.click(within(dialog).getByRole('button', { name: 'Save future weeks' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(skills.calls).toHaveLength(1);
    expect(save.calls[0].body.next_week).toMatchObject({ xp_reward: 20, skill_tags: [{ skill_id: 12, xp_weight: 1 }] });
  });

  it('retains a conflicting draft until the parent explicitly loads refreshed future settings', async () => {
    function ChangingGoal() {
      const [goal, setGoal] = useState(goalWithSchedule());
      return <GoalScheduleControls goal={goal} onReload={async () => {
        const current = goalWithSchedule({ schedule: { revision: 2, paused: false, next_week: { ...NEXT, target: '4' } } });
        setGoal(current);
        return { results: [current] };
      }} />;
    }
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
    const stale = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, () => HttpResponse.json({ error: 'Schedule revision changed.' }, { status: 409 }));
    server.use(stale.handler);
    const { user } = renderWithProviders(<ChangingGoal />);
    const dialog = await edit(user);
    await user.clear(within(dialog).getByLabelText('Future target (miles)'));
    await user.type(within(dialog).getByLabelText('Future target (miles)'), '3');
    await user.click(within(dialog).getByRole('button', { name: 'Save future weeks' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Your draft has been kept.');
    expect(within(dialog).getByLabelText('Future target (miles)')).toHaveValue(3);
    expect(within(dialog).getByRole('button', { name: 'Save future weeks' })).toBeDisabled();
    await user.click(within(dialog).getByRole('button', { name: 'Load saved future settings' }));
    expect(within(dialog).getByLabelText('Future target (miles)')).toHaveValue(4);
    const save = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, { goal_definition_id: 21, schedule: { revision: 3, paused: false, next_week: NEXT } });
    server.use(save.handler);
    await user.click(within(dialog).getByRole('button', { name: 'Save future weeks' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    expect(save.calls[0].body.expected_revision).toBe(2);
    expect(stale.calls).toHaveLength(1);
  });

  it.each(['credential', 'unmount'])('ignores delayed updates after %s changes', async (change) => {
    let finish;
    const save = spyHandler('patch', /\/api\/challenges\/goals\/21\/schedule\/$/, () => new Promise((resolve) => { finish = () => resolve({ goal_definition_id: 21, schedule: { revision: 1, paused: false, next_week: NEXT } }); }));
    server.use(save.handler);
    const { user, onChanged, unmount } = setup();
    const dialog = await edit(user);
    await user.click(within(dialog).getByRole('button', { name: 'Save future weeks' }));
    await waitFor(() => expect(save.calls).toHaveLength(1));
    if (change === 'unmount') unmount();
    else localStorage.setItem('abby_auth_token', 'replacement-session');
    await act(async () => finish());
    expect(onChanged).not.toHaveBeenCalled();
  });

  it('keeps future controls out of child details', async () => {
    setup({ role: 'child' });
    await screen.findByText('Role: child');
    expect(screen.queryByRole('button', { name: 'Pause future weeks' })).not.toBeInTheDocument();
  });
});
