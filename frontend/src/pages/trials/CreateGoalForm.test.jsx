import { beforeEach, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { renderWithProviders, screen, within, waitFor } from '../../test/render';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { buildChallengeGoal } from '../../test/challenges';
import { buildUser } from '../../test/factories';
import CreateGoalForm from './CreateGoalForm';

function renderForm() {
  server.use(http.get('*/api/movement-types/', () => HttpResponse.json([{ id: 3, name: 'Run' }])));
  return renderWithProviders(<CreateGoalForm children={[{ id: 7, display_name: 'Abby' }]} />);
}

beforeEach(() => { server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildUser()))); });

describe('Parent measurable challenges', () => {
  it('creates a recurring 2-mile running goal with a readable preview and exact structured request', async () => {
    const create = spyHandler('post', /\/api\/challenges\/goals\/$/, buildChallengeGoal());
    server.use(create.handler);
    const { user } = renderForm();
    await user.click(screen.getByRole('button', { name: 'Create challenge' }));
    await user.selectOptions(screen.getByLabelText('Activity'), 'movement_session');
    await user.selectOptions(await screen.findByLabelText('Movement activity'), '3');
    await user.selectOptions(screen.getByLabelText('Measure'), 'distance');
    await user.click(screen.getByLabelText('Repeat each week'));
    const preview = screen.getByRole('region', { name: 'Challenge preview' });
    expect(within(preview).getByText('Run · 2 miles this week')).toBeInTheDocument();
    expect(screen.getByText(/Already recorded activity from this week counts/)).toBeInTheDocument();
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Create challenge' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toEqual({ request_id: expect.stringMatching(/^[a-f0-9-]{36}$/), user_id: 7, name: 'Run · 2 miles this week', trigger_type: 'movement_session', movement_type_id: 3, metric: 'distance', target: '2', unit: 'mi', period: 'this_week', repeat_weekly: true, coin_reward: 10, xp_reward: 0, skill_tags: [] });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('submits chosen dates, clears incompatible weekly recurrence, and retains inputs on server rejection', async () => {
    const create = spyHandler('post', /\/api\/challenges\/goals\/$/, () => HttpResponse.json({ target: ['Choose a valid target.'] }, { status: 400 }));
    server.use(create.handler);
    const { user } = renderForm();
    await user.click(screen.getByRole('button', { name: 'Create challenge' }));
    await user.click(screen.getByLabelText('Repeat each week'));
    await user.selectOptions(screen.getByLabelText('Timeframe'), 'custom');
    await user.type(screen.getByLabelText('Start date'), '2026-10-14');
    await user.type(screen.getByLabelText('End date'), '2026-10-21');
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Create challenge' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body).toMatchObject({ period: 'custom', start_date: '2026-10-14', end_date: '2026-10-21', repeat_weekly: false, metric: 'count', target: '2' });
    expect(await screen.findByLabelText('Target')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByLabelText('Start date')).toHaveValue('2026-10-14');
  });


  it('keeps the same request identity when retrying an unchanged failed creation', async () => {
    let requests = 0;
    const create = spyHandler('post', /\/api\/challenges\/goals\/$/, () => {
      requests += 1;
      return requests === 1 ? HttpResponse.json({ error: 'Connection interrupted.' }, { status: 503 }) : buildChallengeGoal();
    });
    server.use(create.handler);
    const { user } = renderForm();
    await user.click(screen.getByRole('button', { name: 'Create challenge' }));
    const submit = () => within(screen.getByRole('dialog')).getByRole('button', { name: 'Create challenge' });
    await user.click(submit());
    expect(await screen.findByRole('alert')).toHaveTextContent('Connection interrupted.');
    await user.click(submit());
    await waitFor(() => expect(create.calls).toHaveLength(2));
    expect(create.calls[1].body).toEqual(create.calls[0].body);
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });


  it('keeps the draft identity after editing an uncertain submission and explains conflicts', async () => {
    const create = spyHandler('post', /\/api\/challenges\/goals\/$/, () => HttpResponse.json({ error: 'Connection interrupted.' }, { status: 503 }));
    server.use(create.handler);
    const { user } = renderForm();
    await user.click(screen.getByRole('button', { name: 'Create challenge' }));
    const submit = () => within(screen.getByRole('dialog')).getByRole('button', { name: 'Create challenge' });
    await user.click(submit());
    await screen.findByRole('alert');
    await user.clear(screen.getByLabelText('Target'));
    await user.type(screen.getByLabelText('Target'), '3');
    const conflict = spyHandler('post', /\/api\/challenges\/goals\/$/, () => HttpResponse.json({ error: 'request_id was already used for different goal details' }, { status: 409 }));
    server.use(conflict.handler);
    await user.click(submit());
    await waitFor(() => expect(conflict.calls).toHaveLength(1));
    expect(conflict.calls[0].body.request_id).toEqual(create.calls[0].body.request_id);
    expect(await screen.findByRole('alert')).toHaveTextContent('This challenge was already saved with different details.');
    expect(screen.getByLabelText('Target')).toHaveValue(3);
    await user.click(screen.getByRole('button', { name: 'New challenge' }));
    expect(screen.getByLabelText('Target')).toHaveValue(2);
    const fresh = spyHandler('post', /\/api\/challenges\/goals\/$/, buildChallengeGoal());
    server.use(fresh.handler);
    await user.click(submit());
    await waitFor(() => expect(fresh.calls).toHaveLength(1));
    expect(fresh.calls[0].body.request_id).not.toEqual(create.calls[0].body.request_id);
  });

  it('rejects fractional count targets with native validation and allows whole targets', async () => {
    const create = spyHandler('post', /\/api\/challenges\/goals\/$/, buildChallengeGoal());
    server.use(create.handler);
    const { user } = renderForm();
    await user.click(screen.getByRole('button', { name: 'Create challenge' }));
    await user.clear(screen.getByLabelText('Target'));
    await user.type(screen.getByLabelText('Target'), '2.5');
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Create challenge' }));
    expect(create.calls).toHaveLength(0);
    expect(screen.getByLabelText('Target')).toBeInvalid();
  });
});
