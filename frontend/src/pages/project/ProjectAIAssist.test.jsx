import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { act, screen, waitFor, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import { buildParent, buildProject, buildUser } from '../../test/factories';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import ProjectNew from '../ProjectNew';
import ProjectDetail from '../ProjectDetail';
import * as api from '../../api';
import { setToken } from '../../api/client';
import { useAuth } from '../../hooks/useApi';
import ProjectAIAssist from './ProjectAIAssist';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

const VERSION = 'a'.repeat(64);
const PLAN = {
  milestones: [{ title: 'Design', description: 'Choose a size.' }, { title: 'Build', description: 'Assemble the pieces.' }],
  steps: [
    { title: 'Sketch', description: 'Draw a plan.', milestone_index: 0 },
    { title: 'Fit panels', description: 'Join the panels.', milestone_index: 1 },
  ],
  materials: [{ name: 'Boards', description: 'Scrap wood.', estimated_cost: '5.00' }],
};

function fixtures(handlers = []) {
  server.use(
    ...handlers,
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent({ family: { id: 1 } }))),
  );
}

async function newProject(handlers = [], ui = <ProjectNew />) {
  fixtures(handlers);
  const view = renderWithProviders(ui);
  await view.user.type(await screen.findByLabelText('Title'), 'Birdhouse');
  return view;
}

async function existingProject(handlers = [], props = {}) {
  fixtures(handlers);
  const view = renderWithProviders(<ProjectAIAssist project={buildProject({ id: 42 })} {...props} />);
  await view.user.click(await screen.findByRole('button', { name: 'AI assist' }));
  const sheet = await screen.findByRole('dialog', { name: 'AI assist' });
  await view.user.click(within(sheet).getByRole('button', { name: 'Draft plan with AI' }));
  await within(sheet).findByLabelText('Step 1 title');
  return { ...view, sheet };
}

describe('Project AI assist', () => {
  it('opens both planning pages without crypto.randomUUID in an insecure browser context', async () => {
    vi.stubGlobal('crypto', { randomUUID: undefined });
    vi.spyOn(api, 'getMe').mockResolvedValue(buildParent());
    vi.spyOn(api, 'getCategories').mockResolvedValue([]);
    vi.spyOn(api, 'getChildren').mockResolvedValue([]);
    vi.spyOn(api, 'getProject').mockResolvedValue(buildProject({ id: 42 }));
    try {
      const first = renderWithProviders(<ProjectNew />);
      expect(await screen.findByLabelText('Title')).toBeInTheDocument();
      first.unmount();
      const second = renderWithProviders(<ProjectDetail />, { route: '/quests/ventures/42', routePath: '/quests/ventures/:id' });
      expect(await screen.findByText('Build a Bird Feeder')).toBeInTheDocument();
      second.unmount();
    } finally {
      vi.restoreAllMocks();
      vi.unstubAllGlobals();
    }
  });

  it('reviews and edits a new plan before one explicit atomic project creation', async () => {
    const generate = spyHandler('post', /\/api\/projects\/plan\/$/, { plan: PLAN, plan_version: null });
    const create = spyHandler('post', /\/api\/projects\/$/, { id: 99 });
    fixtures([generate.handler, create.handler]);
    const { user } = renderWithProviders(<ProjectNew />);
    await user.type(await screen.findByLabelText('Title'), 'Birdhouse');
    await user.type(screen.getByLabelText('Description'), 'Build from scrap wood.');
    await user.type(screen.getByLabelText('Planning guidance'), 'Use hand tools.');
    await user.click(screen.getByRole('button', { name: 'Draft plan with AI' }));
    await screen.findByLabelText('Step 2 title');
    expect(generate.calls).toHaveLength(1);
    expect(generate.calls[0].body).toEqual({ title: 'Birdhouse', description: 'Build from scrap wood.', difficulty: 2, guidance: 'Use hand tools.' });
    expect(create.calls).toHaveLength(0);
    await user.click(screen.getAllByRole('button', { name: 'Remove milestone' })[0]);
    expect(screen.getByLabelText('Step 1 milestone')).toHaveValue('');
    expect(screen.getByLabelText('Step 2 milestone')).toHaveValue('0');
    await user.clear(screen.getByLabelText('Step 2 title'));
    await user.type(screen.getByLabelText('Step 2 title'), 'Fit safely');
    await user.click(screen.getByRole('button', { name: 'Create project' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(create.calls[0].body.plan_create).toEqual({
      ...PLAN,
      milestones: [PLAN.milestones[1]],
      steps: [{ ...PLAN.steps[0], milestone_index: null }, { ...PLAN.steps[1], title: 'Fit safely', milestone_index: 0 }],
    });
    expect(create.calls[0].body).toMatchObject({ title: 'Birdhouse', bonus_amount: '0', payment_kind: 'required' });
  });

  it('adds reviewed additions to an existing project only after explicit confirmation', async () => {
    let applied = false;
    const original = buildProject({
      id: 42, title: 'Birdhouse', bonus_amount: '12.00', parent_notes: 'Private family note',
      milestones: [{ id: 8, title: 'Original phase', is_completed: true, bonus_amount: '7.00' }],
      steps: [{ id: 5, title: 'Finished work', is_completed: true, milestone: 8, resources: [] }],
    });
    const generate = spyHandler('post', /\/api\/projects\/42\/plan\/$/, { plan: PLAN, plan_version: VERSION });
    const apply = spyHandler('post', /\/api\/projects\/42\/apply-plan\/$/, () => { applied = true; return { applied: true }; });
    const read = spyHandler('get', /\/api\/projects\/42\/$/, () => ({ ...original,
      steps: applied ? [...original.steps, { id: 6, title: 'New reviewed step', milestone: null, is_completed: false, resources: [] }] : original.steps,
    }));
    fixtures([generate.handler, apply.handler, read.handler]);
    const { user } = renderWithProviders(<ProjectDetail />, { route: '/quests/ventures/42', routePath: '/quests/ventures/:id' });
    await screen.findByText('Birdhouse');
    await user.click(screen.getByRole('tab', { name: 'Plan' }));
    await user.click(screen.getByRole('button', { name: 'AI assist' }));
    const sheet = await screen.findByRole('dialog', { name: 'AI assist' });
    await user.type(within(sheet).getByLabelText('Planning guidance'), 'Add finishing work.');
    await user.click(within(sheet).getByRole('button', { name: 'Draft plan with AI' }));
    await within(sheet).findByLabelText('Step 1 title');
    expect(generate.calls[0].body).toEqual({ guidance: 'Add finishing work.' });
    expect(apply.calls).toHaveLength(0);
    await user.clear(within(sheet).getByLabelText('Step 1 title'));
    await user.type(within(sheet).getByLabelText('Step 1 title'), 'New reviewed step');
    await user.click(within(sheet).getByRole('button', { name: 'Add to project' }));
    await waitFor(() => expect(apply.calls).toHaveLength(1));
    expect(apply.calls[0].body).toEqual({ plan: { ...PLAN, steps: [{ ...PLAN.steps[0], title: 'New reviewed step' }, PLAN.steps[1]] }, plan_version: VERSION });
    await waitFor(() => expect(read.calls.length).toBeGreaterThanOrEqual(2));
    expect(await screen.findByText('New reviewed step')).toBeInTheDocument();
    expect(screen.getByText('Finished work')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Milestone completed' })).toBeDisabled();
  });

  it('keeps manual planning available after setup fails and retries the same idea', async () => {
    let fail = true;
    const generate = spyHandler('post', /\/api\/projects\/plan\/$/, () => fail
      ? HttpResponse.json({ detail: 'Connect OpenAI or Claude in Planning AI settings.' }, { status: 503 })
      : { plan: PLAN, plan_version: null });
    const { user } = await newProject([generate.handler]);
    await user.click(screen.getByRole('button', { name: 'Draft plan with AI' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Connect OpenAI or Claude');
    expect(screen.getByRole('link', { name: 'Planning AI settings' })).toHaveAttribute('href', '/settings#homework-ai');
    expect(screen.getByLabelText('Title')).toHaveValue('Birdhouse');
    expect(screen.getByRole('button', { name: 'Create project' })).toBeEnabled();
    fail = false;
    await user.click(screen.getByRole('button', { name: 'Draft plan with AI' }));
    expect(await screen.findByLabelText('Step 1 title')).toHaveValue('Sketch');
    expect(generate.calls).toHaveLength(2);
    expect(generate.calls[0].body).toEqual(generate.calls[1].body);
  });

  it('associates rejected planning guidance with its field', async () => {
    const generate = spyHandler('post', /\/api\/projects\/plan\/$/,
      HttpResponse.json({ guidance: ['Describe the tools you have available.'] }, { status: 400 }));
    const { user } = await newProject([generate.handler]);
    await user.type(screen.getByLabelText('Planning guidance'), 'Tools');
    await user.click(screen.getByRole('button', { name: 'Draft plan with AI' }));
    const error = await screen.findByRole('alert');
    expect(error).toHaveTextContent('Describe the tools');
    expect(screen.getByLabelText('Planning guidance').getAttribute('aria-describedby').split(' ')).toContain(error.id);
    expect(generate.calls[0].body.guidance).toBe('Tools');
  });

  it('rejects an unverified generated response and preserves the idea', async () => {
    const generate = spyHandler('post', /\/api\/projects\/plan\/$/, { plan: PLAN, plan_version: VERSION });
    const { user } = await newProject([generate.handler]);
    await user.click(screen.getByRole('button', { name: 'Draft plan with AI' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be verified/i);
    expect(screen.queryByLabelText('Step 1 title')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Title')).toHaveValue('Birdhouse');
  });

  it('confirms regeneration and discard, keeping edits when regeneration fails', async () => {
    let attempt = 0;
    const generate = spyHandler('post', /\/api\/projects\/plan\/$/, () => ++attempt === 1
      ? { plan: PLAN, plan_version: null } : HttpResponse.json({ detail: 'Try drafting later.' }, { status: 503 }));
    const { user } = await newProject([generate.handler]);
    await user.click(screen.getByRole('button', { name: 'Draft plan with AI' }));
    await user.clear(await screen.findByLabelText('Step 1 title'));
    await user.type(screen.getByLabelText('Step 1 title'), 'Keep my edit');
    await user.click(screen.getByRole('button', { name: 'Regenerate plan' }));
    let confirmation = await screen.findByRole('alertdialog', { name: 'Replace this plan draft?' });
    await user.click(within(confirmation).getByRole('button', { name: 'Cancel' }));
    expect(generate.calls).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Regenerate plan' }));
    confirmation = await screen.findByRole('alertdialog');
    await user.click(within(confirmation).getByRole('button', { name: 'Generate new draft' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Try drafting later.');
    expect(screen.getByLabelText('Step 1 title')).toHaveValue('Keep my edit');
    await user.click(screen.getByRole('button', { name: 'Discard plan draft' }));
    confirmation = await screen.findByRole('alertdialog', { name: 'Discard this plan draft?' });
    await user.click(within(confirmation).getByRole('button', { name: 'Cancel' }));
    expect(screen.getByLabelText('Step 1 title')).toHaveValue('Keep my edit');
    await user.click(screen.getByRole('button', { name: 'Discard plan draft' }));
    confirmation = await screen.findByRole('alertdialog');
    await user.click(within(confirmation).getByRole('button', { name: 'Discard draft' }));
    expect(screen.queryByLabelText('Step 1 title')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Title')).toHaveValue('Birdhouse');
    expect(generate.calls).toHaveLength(2);
  });

  it('keeps a stale existing draft and requires regeneration before applying another version', async () => {
    let generations = 0;
    const generate = spyHandler('post', /\/api\/projects\/42\/plan\/$/, () => ({ plan: PLAN,
      plan_version: ++generations === 1 ? VERSION : 'b'.repeat(64) }));
    const apply = spyHandler('post', /\/api\/projects\/42\/apply-plan\/$/, ({ body }) => body.plan_version === VERSION
      ? HttpResponse.json({ detail: 'Project changed.' }, { status: 409 }) : { applied: true });
    const onApplied = vi.fn();
    const onRefresh = vi.fn();
    const { user, sheet } = await existingProject([generate.handler, apply.handler], { onApplied, onRefresh });
    await user.click(within(sheet).getByRole('button', { name: 'Add to project' }));
    expect(await within(sheet).findByRole('alert')).toHaveTextContent('The project changed');
    expect(within(sheet).getByLabelText('Step 1 title')).toHaveValue('Sketch');
    expect(within(sheet).getByRole('button', { name: 'Add to project' })).toBeDisabled();
    expect(onApplied).not.toHaveBeenCalled();
    expect(onRefresh).toHaveBeenCalledOnce();
    await user.click(within(sheet).getByRole('button', { name: 'Regenerate plan' }));
    const confirmation = await screen.findByRole('alertdialog');
    await user.click(within(confirmation).getByRole('button', { name: 'Generate new draft' }));
    await waitFor(() => expect(within(sheet).getByRole('button', { name: 'Add to project' })).toBeEnabled());
    await user.click(within(sheet).getByRole('button', { name: 'Add to project' }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledOnce());
    expect(apply.calls.map(({ body }) => body.plan_version)).toEqual([VERSION, 'b'.repeat(64)]);
  });

  it('keeps the review draft until append is confirmed and allows retry', async () => {
    let confirm = false;
    const generate = spyHandler('post', /\/api\/projects\/42\/plan\/$/, { plan: PLAN, plan_version: VERSION });
    const apply = spyHandler('post', /\/api\/projects\/42\/apply-plan\/$/, () => ({ applied: confirm }));
    const onApplied = vi.fn();
    const { user, sheet } = await existingProject([generate.handler, apply.handler], { onApplied });
    await user.click(within(sheet).getByRole('button', { name: 'Add to project' }));
    expect(await within(sheet).findByRole('alert')).toHaveTextContent('The plan could not be confirmed');
    expect(onApplied).not.toHaveBeenCalled();
    expect(within(sheet).getByLabelText('Step 1 title')).toHaveValue('Sketch');
    confirm = true;
    await user.click(within(sheet).getByRole('button', { name: 'Add to project' }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledOnce());
    expect(apply.calls).toHaveLength(2);
    expect(apply.calls[1].body).toEqual(apply.calls[0].body);
  });

  it('prevents duplicate generation and creation while a plan is pending and rejects stale idea responses', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const started = vi.fn();
    const mutation = vi.spyOn(api, 'draftProjectPlan');
    const create = spyHandler('post', /\/api\/projects\/$/, { id: 99 });
    const { user } = await newProject([create.handler, http.post('*/api/projects/plan/', async () => {
      started(); await pending; return HttpResponse.json({ plan: PLAN, plan_version: null });
    })]);
    try {
      await user.click(screen.getByRole('button', { name: 'Draft plan with AI' }));
      await waitFor(() => expect(started).toHaveBeenCalledOnce());
      expect(screen.getByRole('button', { name: 'Drafting…' })).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Create project' })).toBeDisabled();
      await user.click(screen.getByRole('button', { name: 'Drafting…' }));
      await user.click(screen.getByRole('button', { name: 'Create project' }));
      await user.type(screen.getByLabelText('Title'), ' revised');
      await act(async () => { release(); await mutation.mock.results[0].value; });
      expect(await screen.findByRole('alert')).toHaveTextContent('Your project idea changed');
      expect(screen.queryByLabelText('Step 1 title')).not.toBeInTheDocument();
      expect(started).toHaveBeenCalledOnce();
      expect(create.calls).toHaveLength(0);
      expect(screen.getByLabelText('Title')).toHaveValue('Birdhouse revised');
    } finally { release(); mutation.mockRestore(); }
  });

  it.each(['account', 'credential', 'unmount'])('ignores a late new-plan response after %s changes', async (change) => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const mutation = vi.spyOn(api, 'draftProjectPlan');
    function SwitchAccount() {
      const { setUser } = useAuth();
      return <><button onClick={() => {
        if (change === 'credential') setToken('synthetic-replacement-credential');
        setUser(buildParent({ id: change === 'account' ? 100 : 99, family: { id: 1 } }));
      }}>Change session</button><ProjectNew /></>;
    }
    const view = await newProject([http.post('*/api/projects/plan/', async () => {
      await pending; return HttpResponse.json({ plan: PLAN, plan_version: null });
    })], <SwitchAccount />);
    try {
      await view.user.click(screen.getByRole('button', { name: 'Draft plan with AI' }));
      await waitFor(() => expect(mutation).toHaveBeenCalledOnce());
      if (change === 'unmount') view.unmount();
      else await view.user.click(screen.getByRole('button', { name: 'Change session' }));
      await act(async () => { release(); await mutation.mock.results[0].value; });
      expect(screen.queryByLabelText('Step 1 title')).not.toBeInTheDocument();
      if (change !== 'unmount') expect(await screen.findByLabelText('Title')).toHaveValue('');
    } finally { release(); mutation.mockRestore(); }
  });

  it('hides planning controls and does not request a draft for a child', async () => {
    const generate = spyHandler('post', /\/api\/projects\/42\/plan\/$/, { plan: PLAN, plan_version: VERSION });
    fixtures([generate.handler, http.get('*/api/auth/me/', () => HttpResponse.json(buildUser()))]);
    renderWithProviders(<><ProjectNew /><ProjectAIAssist project={buildProject({ id: 42 })} /></>);
    expect(await screen.findByText('Only parents can create projects.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'AI assist' })).not.toBeInTheDocument();
    expect(generate.calls).toHaveLength(0);
  });

  it('validates the reviewed draft before creating a project', async () => {
    const generate = spyHandler('post', /\/api\/projects\/plan\/$/, { plan: PLAN, plan_version: null });
    const create = spyHandler('post', /\/api\/projects\/$/, { id: 99 });
    const { user } = await newProject([generate.handler, create.handler]);
    await user.click(screen.getByRole('button', { name: 'Draft plan with AI' }));
    await screen.findByLabelText('Step 1 title');
    await user.click(screen.getAllByRole('button', { name: 'Remove step' })[0]);
    await user.click(screen.getByRole('button', { name: 'Remove step' }));
    await user.click(screen.getByRole('button', { name: 'Create project' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Keep at least one step');
    expect(create.calls).toHaveLength(0);
    expect(screen.getByLabelText('Milestone 1 title')).toHaveValue('Design');
  });

  it('prevents duplicate append requests and ignores success after the credential changes', async () => {
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const mutation = vi.spyOn(api, 'applyProjectPlan');
    const onApplied = vi.fn();
    const started = vi.fn();
    const generate = spyHandler('post', /\/api\/projects\/42\/plan\/$/, { plan: PLAN, plan_version: VERSION });
    const { user, sheet } = await existingProject([generate.handler, http.post('*/api/projects/42/apply-plan/', async () => {
      started(); await pending; return HttpResponse.json({ applied: true });
    })], { onApplied });
    try {
      await user.click(within(sheet).getByRole('button', { name: 'Add to project' }));
      await waitFor(() => expect(started).toHaveBeenCalledOnce());
      expect(within(sheet).getByRole('button', { name: 'Adding…' })).toBeDisabled();
      await user.click(within(sheet).getByRole('button', { name: 'Adding…' }));
      act(() => setToken('synthetic-replacement-credential'));
      await act(async () => { release(); await mutation.mock.results[0].value; });
      expect(started).toHaveBeenCalledOnce();
      expect(onApplied).not.toHaveBeenCalled();
      expect(screen.queryByRole('dialog', { name: 'AI assist' })).not.toBeInTheDocument();
    } finally { release(); mutation.mockRestore(); }
  });
});
