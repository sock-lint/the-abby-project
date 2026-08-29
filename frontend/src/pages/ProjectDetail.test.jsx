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
      HttpResponse.json(buildProject({ id: 42, title: 'TestPrj', ...projectOverrides })),
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
  it('renders project title and tabs', async () => {
    renderPage(buildUser());
    await waitFor(() => expect(screen.getByText('TestPrj')).toBeInTheDocument());
    expect(screen.getAllByText(/overview|plan|materials/i).length).toBeGreaterThan(0);
  });

  it('shows "not inscribed" when project is null', async () => {
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
    await waitFor(() => expect(screen.getByText(/not inscribed/i)).toBeInTheDocument());
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
    expect(screen.queryByText(/not inscribed/i)).toBeNull();

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

  it('marking a material purchased posts to /projects/{pid}/materials/{mid}/mark-purchased/', async () => {
    const user = userEvent.setup();
    const mark = spyHandler('post', /\/api\/projects\/\d+\/materials\/\d+\/mark-purchased\/$/, { ok: true });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get(/\/api\/projects\/42\/$/, () =>
        HttpResponse.json(buildProject({
          id: 42, title: 'TestPrj',
          materials: [{ id: 11, name: 'Plywood', estimated_cost: '5.00', is_purchased: false }],
        })),
      ),
      mark.handler,
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
    await user.click(screen.getByRole('tab', { name: /^materials$/i }));
    const purchasedBtn = await screen.findByRole('button', { name: /mark purchased/i });
    await user.click(purchasedBtn);

    await waitFor(() => expect(mark.calls).toHaveLength(1));
    expect(mark.calls[0].url).toMatch(/\/projects\/42\/materials\/11\/mark-purchased\/$/);
    expect(mark.calls[0].body).toEqual({ actual_cost: '5.00' });
  });
});
