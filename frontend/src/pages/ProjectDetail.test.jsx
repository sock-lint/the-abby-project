import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ProjectDetail from './ProjectDetail.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildProject, buildUser } from '../test/factories.js';

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

  it('switches between tabs', async () => {
    const user = userEvent.setup();
    renderPage(buildUser());
    await waitFor(() => expect(screen.getByText('TestPrj')).toBeInTheDocument());
    const planTab = screen.getByRole('button', { name: /^plan$/i });
    await user.click(planTab);
    const materialsTab = screen.getByRole('button', { name: /^materials$/i });
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
    await user.click(screen.getByRole('button', { name: /^plan$/i }));
    const stepBtn = await screen.findByRole('button', { name: /mark step complete/i });
    await user.click(stepBtn);

    await waitFor(() => expect(complete.calls).toHaveLength(1));
    expect(complete.calls[0].url).toMatch(/\/projects\/42\/steps\/5\/complete\/$/);
  });

  it('completing a milestone posts to /projects/{pid}/milestones/{mid}/complete/', async () => {
    const user = userEvent.setup();
    const complete = spyHandler('post', /\/api\/projects\/\d+\/milestones\/\d+\/complete\/$/, { ok: true });
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
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
    await user.click(screen.getByRole('button', { name: /^plan$/i }));
    const msBtn = await screen.findByRole('button', { name: /mark milestone complete/i });
    await user.click(msBtn);

    await waitFor(() => expect(complete.calls).toHaveLength(1));
    expect(complete.calls[0].url).toMatch(/\/projects\/42\/milestones\/8\/complete\/$/);
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
    await user.click(screen.getByRole('button', { name: /^materials$/i }));
    const purchasedBtn = await screen.findByRole('button', { name: /mark purchased/i });
    await user.click(purchasedBtn);

    await waitFor(() => expect(mark.calls).toHaveLength(1));
    expect(mark.calls[0].url).toMatch(/\/projects\/42\/materials\/11\/mark-purchased\/$/);
    expect(mark.calls[0].body).toEqual({ actual_cost: '5.00' });
  });
});
