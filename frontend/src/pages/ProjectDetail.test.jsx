import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ProjectDetail from './ProjectDetail.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
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
});
