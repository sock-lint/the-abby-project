import { selectDropdown } from '../test/selectDropdown';
import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ProjectDetail from './ProjectDetail.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildParent, buildProject, buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage(user, projectOverrides = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    http.get(/\/api\/projects\/42\/$/, () =>
      HttpResponse.json(buildProject({ id: 42, title: 'TestPrj', ...(typeof projectOverrides === 'function' ? projectOverrides() : projectOverrides) })),
    ),
  );
  return render(
    <MemoryRouter initialEntries={['/quests/ventures/42']}>
      <AuthProvider>
        <Routes>
          <Route path="/quests/ventures/:id" element={<ProjectDetail />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('ProjectDetail', () => {
  it('opens homework steps with a route back to homework and saves step progress', async () => {
    const user = userEvent.setup();
    const step = { id: 5, title: 'Read chapter one', is_completed: false, milestone: null };
    const complete = spyHandler('post', '*/api/projects/42/steps/5/complete/', () => {
      step.is_completed = true;
      return step;
    });
    server.use(complete.handler);
    renderPage(buildUser(), () => ({
      is_homework_plan: true, homework_assignment_id: 17, status: 'in_progress',
      steps: [step], bonus_amount: '13.00', xp_reward: 99,
    }));
    expect(await screen.findByText('Homework plan')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to Homework' })).toHaveAttribute('href', '/quests?tab=study');
    expect(screen.getByText(/submit your homework from the Homework tab/i)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Plan' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByRole('button', { name: /work on this project|submit for review/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Mark step complete' }));
    await waitFor(() => expect(complete.calls).toHaveLength(1));
    expect(complete.calls[0].url).toMatch(/\/api\/projects\/42\/steps\/5\/complete\/$/);
    expect(complete.calls[0].body).toBeNull();
    expect(await screen.findByRole('button', { name: 'Uncheck step' })).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Overview' }));
    expect(screen.queryByText(/cash reward|^bonus$|xp reward/i)).not.toBeInTheDocument();
  });

  it('lets a parent finish a homework phase without promising its old bonus', async () => {
    const user = userEvent.setup();
    const complete = spyHandler('post', '*/api/projects/42/milestones/8/complete/', {});
    server.use(complete.handler);
    renderPage(buildParent(), { is_homework_plan: true, milestones: [{ id: 8, title: 'Research', bonus_amount: '9.00', is_completed: false }] });
    await user.click(await screen.findByRole('button', { name: 'Mark milestone complete' }));
    const dialog = await screen.findByRole('alertdialog', { name: /mark this milestone complete/i });
    expect(dialog).not.toHaveTextContent(/pay|\$9\.00/i);
    await user.click(within(dialog).getByRole('button', { name: 'Mark complete' }));
    await waitFor(() => expect(complete.calls).toHaveLength(1));
    expect(complete.calls[0].url).toMatch(/\/api\/projects\/42\/milestones\/8\/complete\/$/);
    expect(complete.calls[0].body).toBeNull();
  });

  it('renders project title and tabs', async () => {
    renderPage(buildUser());
    await waitFor(() => expect(screen.getByText('TestPrj')).toBeInTheDocument());
    expect(screen.getAllByText(/overview|plan|materials/i).length).toBeGreaterThan(0);
  });

  it('shows "project is unavailable" when project is null', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get(/\/api\/projects\/42\/$/, () =>
        HttpResponse.json(null),
      ),
    );
    render(
      <MemoryRouter initialEntries={['/quests/ventures/42']}>
        <AuthProvider>
          <Routes>
            <Route path="/quests/ventures/:id" element={<ProjectDetail />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/project is unavailable/i)).toBeInTheDocument());
  });

  it('offers a retry on a failed fetch rather than the "may have been deleted" copy', async () => {
    const user = userEvent.setup();
    let attempt = 0;
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get(/\/api\/projects\/42\/$/, () => {
        attempt += 1;
        return attempt === 1
          ? HttpResponse.json({ error: 'gateway timeout' }, { status: 504 })
          : HttpResponse.json(buildProject({ id: 42, title: 'TestPrj' }));
      }),
    );
    render(
      <MemoryRouter initialEntries={['/quests/ventures/42']}>
        <AuthProvider>
          <Routes>
            <Route path="/quests/ventures/:id" element={<ProjectDetail />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(/gateway timeout/i);
    expect(screen.queryByText(/project is unavailable/i)).toBeNull();

    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByText('TestPrj')).toBeInTheDocument();
  });

  it('surfaces a failed step toggle instead of silently doing nothing', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get(/\/api\/projects\/42\/$/, () =>
        HttpResponse.json(buildProject({
          id: 42, title: 'TestPrj',
          steps: [{ id: 5, title: 'Cut wood', is_completed: false, milestone: null }],
        })),
      ),
      http.post(/\/api\/projects\/\d+\/steps\/\d+\/complete\/$/, () =>
        HttpResponse.json({ error: 'step is locked' }, { status: 400 }),
      ),
    );
    render(
      <MemoryRouter initialEntries={['/quests/ventures/42']}>
        <AuthProvider>
          <Routes>
            <Route path="/quests/ventures/:id" element={<ProjectDetail />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText('TestPrj')).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /^plan$/i }));
    await user.click(await screen.findByRole('button', { name: /mark step complete/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/step is locked/i);
  });

  it('surfaces a failed milestone delete instead of looking like a success', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get(/\/api\/projects\/42\/$/, () =>
        HttpResponse.json(buildProject({
          id: 42, title: 'TestPrj',
          milestones: [{ id: 8, title: 'Frame', is_completed: false }],
          steps: [],
        })),
      ),
      http.delete(/\/api\/projects\/\d+\/milestones\/\d+\/$/, () =>
        HttpResponse.json({ error: 'milestone already paid out' }, { status: 409 }),
      ),
    );
    render(
      <MemoryRouter initialEntries={['/quests/ventures/42']}>
        <AuthProvider>
          <Routes>
            <Route path="/quests/ventures/:id" element={<ProjectDetail />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText('TestPrj')).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /^plan$/i }));
    await user.click(await screen.findByRole('button', { name: /delete milestone/i }));
    const dialog = await screen.findByRole('alertdialog', { name: /delete this milestone/i });
    await user.click(within(dialog).getByRole('button', { name: /^delete$/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/already paid out/i);
  });

  it('switches between tabs', async () => {
    const user = userEvent.setup();
    renderPage(buildUser());
    await waitFor(() => expect(screen.getByText('TestPrj')).toBeInTheDocument());
    const planTab = screen.getByRole('tab', { name: /^plan$/i });
    await user.click(planTab);
    const materialsTab = screen.getByRole('tab', { name: /^materials$/i });
    await user.click(materialsTab);
  });

  it('checking a step posts to /projects/{pid}/steps/{sid}/complete/', async () => {
    const user = userEvent.setup();
    const complete = spyHandler('post', /\/api\/projects\/\d+\/steps\/\d+\/complete\/$/, { ok: true });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get(/\/api\/projects\/42\/$/, () =>
        HttpResponse.json(buildProject({
          id: 42, title: 'TestPrj',
          steps: [{ id: 5, title: 'Cut wood', is_completed: false, milestone: null }],
        })),
      ),
      complete.handler,
    );
    render(
      <MemoryRouter initialEntries={['/quests/ventures/42']}>
        <AuthProvider>
          <Routes>
            <Route path="/quests/ventures/:id" element={<ProjectDetail />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText('TestPrj')).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /^plan$/i }));
    const stepBtn = await screen.findByRole('button', { name: /mark step complete/i });
    await user.click(stepBtn);

    await waitFor(() => expect(complete.calls).toHaveLength(1));
    expect(complete.calls[0].url).toMatch(/\/projects\/42\/steps\/5\/complete\/$/);
  });

  // Parent-only: completing a milestone posts a milestone_bonus to
  // PaymentLedger, and the server refuses it from a child.
  it('completing a milestone posts to /projects/{pid}/milestones/{mid}/complete/', async () => {
    const user = userEvent.setup();
    const complete = spyHandler('post', /\/api\/projects\/\d+\/milestones\/\d+\/complete\/$/, { ok: true });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get(/\/api\/projects\/42\/$/, () =>
        HttpResponse.json(buildProject({
          id: 42, title: 'TestPrj',
          milestones: [{ id: 8, title: 'Frame', bonus_amount: '2.00', is_completed: false }],
          steps: [],
        })),
      ),
      complete.handler,
    );
    render(
      <MemoryRouter initialEntries={['/quests/ventures/42']}>
        <AuthProvider>
          <Routes>
            <Route path="/quests/ventures/:id" element={<ProjectDetail />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText('TestPrj')).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /^plan$/i }));
    const msBtn = await screen.findByRole('button', { name: /mark milestone complete/i });
    await user.click(msBtn);

    // Completing a milestone pays out its bonus, so it goes through a confirm
    // first — the circle sits right beside the accordion toggle.
    const dialog = await screen.findByRole('alertdialog', { name: /mark this milestone complete/i });
    expect(dialog).toHaveTextContent('$2.00');
    await user.click(within(dialog).getByRole('button', { name: /^mark complete$/i }));

    await waitFor(() => expect(complete.calls).toHaveLength(1));
    expect(complete.calls[0].url).toMatch(/\/projects\/42\/milestones\/8\/complete\/$/);
  });

  // The kid does the work but a parent closes the milestone out, so a child
  // must not be shown a control the API answers with 403.
  it('shows a child the milestone state without an actionable control', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), {
      milestones: [{ id: 8, title: 'Frame', bonus_amount: '2.00', is_completed: false }],
      steps: [{ id: 5, title: 'Cut wood', is_completed: true, milestone: 8 }],
    });

    await waitFor(() => expect(screen.getByText('TestPrj')).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /^plan$/i }));

    expect(await screen.findByText('Frame')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /mark milestone complete/i })).toBeNull();
    // …and with every step done, the kid is told what happens next rather
    // than being offered the parent's button.
    expect(screen.getByText(/a parent closes this one out/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /all steps done/i }),
    ).toBeNull();
  });

  it('marks an existing or borrowed supply ready without recording a purchase and reloads saved readiness', async () => {
    const user = userEvent.setup();
    const material = { id: 11, name: 'Class notes', estimated_cost: '5.00', actual_cost: null, is_purchased: false, is_ready: false };
    let reads = 0;
    const ready = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-ready\/$/, () => {
      material.is_ready = true;
      return material;
    });
    const purchase = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-purchased\/$/, {});
    server.use(ready.handler, purchase.handler);
    renderPage(buildUser(), () => { reads += 1; return { materials: [material] }; });

    await screen.findByText('TestPrj');
    await user.click(screen.getByRole('tab', { name: /^materials$/i }));
    await user.click(await screen.findByRole('button', { name: /^mark ready$/i }));
    const dialog = await screen.findByRole('dialog', { name: /mark material ready/i });
    expect(within(dialog).getByRole('combobox', { name: /how did you get it/i })).toHaveValue('on_hand');
    expect(within(dialog).queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(ready.calls).toHaveLength(0);
    await user.click(within(dialog).getByRole('button', { name: /^mark ready$/i }));

    await waitFor(() => expect(ready.calls).toHaveLength(1));
    expect(ready.calls[0].url).toMatch(/\/projects\/42\/materials\/11\/mark-ready\/$/);
    expect(ready.calls[0].body).toEqual({});
    expect(purchase.calls).toHaveLength(0);
    expect(await screen.findByText('Ready')).toBeInTheDocument();
    expect(reads).toBe(2);
    expect(screen.getByText('spent $0.00')).toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByText(/actual:/i)).not.toBeInTheDocument();
  });

  it.each(['3.75', '0.00'])('records an explicitly entered purchase cost of %s instead of its estimate', async (cost) => {
    const user = userEvent.setup();
    const material = { id: 11, name: 'Plywood', estimated_cost: '5.00', actual_cost: null, is_purchased: false, is_ready: false };
    const purchase = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-purchased\/$/, ({ body }) => {
      Object.assign(material, { actual_cost: body.actual_cost, is_purchased: true, is_ready: true });
      return material;
    });
    const ready = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-ready\/$/, {});
    server.use(purchase.handler, ready.handler);
    renderPage(buildUser(), { materials: [material] });

    await screen.findByText('TestPrj');
    await user.click(screen.getByRole('tab', { name: /^materials$/i }));
    await user.click(await screen.findByRole('button', { name: /^mark ready$/i }));
    const dialog = await screen.findByRole('dialog', { name: /mark material ready/i });
    await selectDropdown(user, within(dialog).getByRole('combobox', { name: /how did you get it/i }), 'purchased');
    const input = within(dialog).getByRole('spinbutton', { name: /actual cost/i });
    expect(input).toHaveValue(null);
    expect(within(dialog).getByRole('button', { name: /^mark ready$/i })).toBeDisabled();
    await user.type(input, cost);
    await user.click(within(dialog).getByRole('button', { name: /^mark ready$/i }));

    await waitFor(() => expect(purchase.calls).toHaveLength(1));
    expect(purchase.calls[0].url).toMatch(/\/projects\/42\/materials\/11\/mark-purchased\/$/);
    expect(purchase.calls[0].body).toEqual({ actual_cost: cost });
    expect(ready.calls).toHaveLength(0);
    expect(await screen.findByText('Ready')).toBeInTheDocument();
    expect(screen.getByText(`spent $${cost}`)).toBeInTheDocument();
    expect(screen.getByText(`est: $5.00 · actual: $${cost}`)).toBeInTheDocument();
  });

  it('corrects an on-hand material to still needed without recording a purchase', async () => {
    const user = userEvent.setup();
    const material = { id: 11, name: 'Calculator', estimated_cost: '20.00', actual_cost: null, is_purchased: false, is_ready: true };
    const notReady = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-not-ready\/$/, () => {
      material.is_ready = false;
      return material;
    });
    const purchase = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-purchased\/$/, {});
    server.use(notReady.handler, purchase.handler);
    renderPage(buildUser(), { materials: [material] });

    await screen.findByText('TestPrj');
    await user.click(screen.getByRole('tab', { name: /^materials$/i }));
    await user.click(await screen.findByRole('button', { name: 'Change readiness for Calculator' }));
    const dialog = await screen.findByRole('dialog', { name: /update material readiness/i });
    await selectDropdown(user, within(dialog).getByRole('combobox'), 'needed');
    expect(within(dialog).queryByRole('spinbutton')).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: /^mark not ready$/i }));

    expect(await screen.findByRole('button', { name: /^mark ready$/i })).toBeInTheDocument();
    expect(screen.queryByText('Ready')).not.toBeInTheDocument();
    expect(notReady.calls).toHaveLength(1);
    expect(notReady.calls[0].url).toMatch(/\/projects\/42\/materials\/11\/mark-not-ready\/$/);
    expect(notReady.calls[0].body).toEqual({});
    expect(purchase.calls).toHaveLength(0);
    expect(screen.getByText('spent $0.00')).toBeInTheDocument();
  });

  it('records a later purchase for a material previously marked on hand', async () => {
    const user = userEvent.setup();
    const material = { id: 11, name: 'Calculator', estimated_cost: '20.00', actual_cost: null, is_purchased: false, is_ready: true };
    const purchase = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-purchased\/$/, ({ body }) => {
      Object.assign(material, { actual_cost: body.actual_cost, is_purchased: true });
      return material;
    });
    server.use(purchase.handler);
    renderPage(buildUser(), { materials: [material] });

    await screen.findByText('TestPrj');
    await user.click(screen.getByRole('tab', { name: /^materials$/i }));
    await user.click(await screen.findByRole('button', { name: 'Change readiness for Calculator' }));
    const dialog = await screen.findByRole('dialog', { name: /update material readiness/i });
    await selectDropdown(user, within(dialog).getByRole('combobox'), 'purchased');
    await user.type(within(dialog).getByRole('spinbutton', { name: /actual cost/i }), '12.50');
    await user.click(within(dialog).getByRole('button', { name: /^mark ready$/i }));

    expect(await screen.findByText('spent $12.50')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Change readiness for Calculator' })).not.toBeInTheDocument();
    expect(purchase.calls).toHaveLength(1);
    expect(purchase.calls[0].url).toMatch(/\/projects\/42\/materials\/11\/mark-purchased\/$/);
    expect(purchase.calls[0].body).toEqual({ actual_cost: '12.50' });
  });

  it('retains a failed readiness choice for retry without claiming a saved result', async () => {
    const user = userEvent.setup();
    const material = { id: 11, name: 'Calculator', estimated_cost: '10.00', actual_cost: null, is_purchased: false, is_ready: false };
    let reads = 0;
    const ready = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-ready\/$/, HttpResponse.json({ error: 'Could not save readiness' }, { status: 503 }));
    server.use(ready.handler);
    renderPage(buildUser(), () => { reads += 1; return { materials: [material] }; });

    await screen.findByText('TestPrj');
    await user.click(screen.getByRole('tab', { name: /^materials$/i }));
    await user.click(await screen.findByRole('button', { name: /^mark ready$/i }));
    const dialog = await screen.findByRole('dialog', { name: /mark material ready/i });
    await user.click(within(dialog).getByRole('button', { name: /^mark ready$/i }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Could not save readiness');
    expect(ready.calls).toHaveLength(1);
    expect(ready.calls[0].body).toEqual({});
    expect(reads).toBe(1);
    expect(screen.queryByText('Ready')).not.toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /^mark ready$/i })).toBeEnabled();

    const retry = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-ready\/$/, () => {
      material.is_ready = true;
      return material;
    });
    server.use(retry.handler);
    await user.click(within(dialog).getByRole('button', { name: /^mark ready$/i }));
    expect(await screen.findByText('Ready')).toBeInTheDocument();
    expect(retry.calls).toHaveLength(1);
    expect(retry.calls[0].body).toEqual({});
  });

  it('shows purchase field errors beside the entered cost without discarding the value', async () => {
    const user = userEvent.setup();
    const purchase = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-purchased\/$/, HttpResponse.json({ actual_cost: ['Enter a valid amount.'] }, { status: 400 }));
    server.use(purchase.handler);
    renderPage(buildUser(), { materials: [{ id: 11, name: 'Paper', estimated_cost: '5.00', is_purchased: false }] });

    await screen.findByText('TestPrj');
    await user.click(screen.getByRole('tab', { name: /^materials$/i }));
    await user.click(await screen.findByRole('button', { name: /^mark ready$/i }));
    const dialog = await screen.findByRole('dialog', { name: /mark material ready/i });
    await selectDropdown(user, within(dialog).getByRole('combobox', { name: /how did you get it/i }), 'purchased');
    const input = within(dialog).getByRole('spinbutton', { name: /actual cost/i });
    await user.type(input, '1.25');
    await user.click(within(dialog).getByRole('button', { name: /^mark ready$/i }));

    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Enter a valid amount.');
    expect(input).toHaveValue(1.25);
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(purchase.calls).toHaveLength(1);
    expect(purchase.calls[0].body).toEqual({ actual_cost: '1.25' });
  });

  it('retains an entered purchase amount when a passive dismissal is canceled', async () => {
    const user = userEvent.setup();
    const material = { id: 11, name: 'Paper', estimated_cost: '5.00', is_purchased: false };
    const purchase = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-purchased\/$/, ({ body }) => {
      Object.assign(material, { actual_cost: body.actual_cost, is_purchased: true, is_ready: true });
      return material;
    });
    server.use(purchase.handler);
    renderPage(buildUser(), { materials: [material] });

    await screen.findByText('TestPrj');
    await user.click(screen.getByRole('tab', { name: /^materials$/i }));
    await user.click(await screen.findByRole('button', { name: /^mark ready$/i }));
    const dialog = await screen.findByRole('dialog', { name: /mark material ready/i });
    await selectDropdown(user, within(dialog).getByRole('combobox'), 'purchased');
    const input = within(dialog).getByRole('spinbutton', { name: /actual cost/i });
    await user.type(input, '2.25');
    await user.keyboard('{Escape}');

    const discard = await screen.findByRole('alertdialog', { name: /discard changes/i });
    expect(purchase.calls).toHaveLength(0);
    await user.click(within(discard).getByRole('button', { name: /^cancel$/i }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(input).toHaveValue(2.25);
    expect(within(dialog).getByRole('combobox')).toHaveValue('purchased');
    await user.click(within(dialog).getByRole('button', { name: /^mark ready$/i }));

    expect(await screen.findByText('Ready')).toBeInTheDocument();
    expect(purchase.calls).toHaveLength(1);
    expect(purchase.calls[0].body).toEqual({ actual_cost: '2.25' });
  });

  it('keeps the sheet open and blocks duplicate submits or cancellation while saving', async () => {
    const user = userEvent.setup();
    const material = { id: 11, name: 'Calculator', estimated_cost: '10.00', is_purchased: false, is_ready: false };
    let finish;
    const body = new ReadableStream({
      start(controller) {
        finish = () => {
          material.is_ready = true;
          controller.enqueue(new TextEncoder().encode(JSON.stringify(material)));
          controller.close();
        };
      },
    });
    const ready = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-ready\/$/, new HttpResponse(body, { headers: { 'Content-Type': 'application/json' } }));
    server.use(ready.handler);
    renderPage(buildUser(), { materials: [material] });

    await screen.findByText('TestPrj');
    await user.click(screen.getByRole('tab', { name: /^materials$/i }));
    await user.click(await screen.findByRole('button', { name: /^mark ready$/i }));
    const dialog = await screen.findByRole('dialog', { name: /mark material ready/i });
    const submit = within(dialog).getByRole('button', { name: /^mark ready$/i });
    await user.dblClick(submit);
    await waitFor(() => expect(ready.calls).toHaveLength(1));
    expect(submit).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: /^cancel$/i })).toBeDisabled();
    expect(within(dialog).getByRole('combobox')).toBeDisabled();
    await user.keyboard('{Escape}');
    expect(dialog).toBeInTheDocument();

    finish();
    expect(await screen.findByText('Ready')).toBeInTheDocument();
    expect(ready.calls).toHaveLength(1);
    expect(ready.calls[0].body).toEqual({});
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('cancels a readiness choice without writing anything', async () => {
    const user = userEvent.setup();
    const ready = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-ready\/$/, {});
    const purchase = spyHandler('post', /\/api\/projects\/42\/materials\/11\/mark-purchased\/$/, {});
    server.use(ready.handler, purchase.handler);
    renderPage(buildUser(), { materials: [{ id: 11, name: 'Notes', estimated_cost: '0.00', is_purchased: false }] });

    await screen.findByText('TestPrj');
    await user.click(screen.getByRole('tab', { name: /^materials$/i }));
    const opener = await screen.findByRole('button', { name: /^mark ready$/i });
    await user.click(opener);
    const dialog = await screen.findByRole('dialog', { name: /mark material ready/i });
    await user.click(within(dialog).getByRole('button', { name: /^cancel$/i }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(ready.calls).toHaveLength(0);
    expect(purchase.calls).toHaveLength(0);
    expect(opener).toHaveFocus();
  });
});
