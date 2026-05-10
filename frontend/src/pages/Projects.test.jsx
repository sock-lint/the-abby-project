import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import Projects from './Projects.jsx';
import { AuthProvider } from '../hooks/useApi.js';
import { server } from '../test/server.js';
import { buildParent, buildProject, buildUser } from '../test/factories.js';

function renderPage(user = buildUser(), handlers = []) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Projects />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('Projects', () => {
  it('renders the empty state when there are no ventures', async () => {
    renderPage(buildUser(), [
      http.get('*/api/projects/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/no ventures yet/i)).toBeInTheDocument(),
    );
  });

  it('shows "New venture" only for parents', async () => {
    renderPage(buildParent(), [
      http.get('*/api/projects/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText(/new venture/i)).toBeInTheDocument());
  });

  it('renders a list of projects with metadata', async () => {
    renderPage(buildUser(), [
      http.get('*/api/projects/', () =>
        HttpResponse.json([
          buildProject({ id: 1, title: 'Alpha', difficulty: 4, payment_kind: 'bounty', milestones_total: 3, milestones_completed: 1, assigned_to: null, cover_photo: '/c.jpg', category: { name: 'Art', icon: '🎨' } }),
          buildProject({ id: 2, title: 'Beta', assigned_to: buildUser({ display_name: 'Abby' }) }),
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
    expect(screen.getByText('Beta')).toBeInTheDocument();
    expect(screen.getByText(/open bounty/i)).toBeInTheDocument();
    expect(screen.getByText(/assigned to abby/i)).toBeInTheDocument();
  });

  it('filters by status', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/projects/', () =>
        HttpResponse.json([
          buildProject({ id: 1, title: 'LivingP', status: 'active' }),
          buildProject({ id: 2, title: 'FinishedP', status: 'completed' }),
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('LivingP')).toBeInTheDocument());
    const [statusSelect] = screen.getAllByRole('combobox');
    await user.selectOptions(statusSelect, 'completed');
    expect(screen.queryByText('LivingP')).toBeNull();
    expect(screen.getByText('FinishedP')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    expect(screen.getByText('LivingP')).toBeInTheDocument();
  });

  it('filters by type', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/projects/', () =>
        HttpResponse.json([
          buildProject({ id: 1, title: 'ReqP', payment_kind: 'required' }),
          buildProject({ id: 2, title: 'BountyP', payment_kind: 'bounty' }),
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('ReqP')).toBeInTheDocument());
    const [, typeSelect] = screen.getAllByRole('combobox');
    await user.selectOptions(typeSelect, 'bounty');
    expect(screen.queryByText('ReqP')).toBeNull();
    expect(screen.getByText('BountyP')).toBeInTheDocument();
  });

  it('filters by child + unassigned (parent only)', async () => {
    const user = userEvent.setup();
    renderPage(buildParent(), [
      http.get('*/api/children/', () =>
        HttpResponse.json([buildUser({ id: 3, display_name: 'Abby' })]),
      ),
      http.get('*/api/projects/', () =>
        HttpResponse.json([
          buildProject({ id: 1, title: 'Abby P', assigned_to: { id: 3, display_name: 'Abby' } }),
          buildProject({ id: 2, title: 'Open', assigned_to: null }),
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('Abby P')).toBeInTheDocument());
    const [, , childSelect] = screen.getAllByRole('combobox');
    await user.selectOptions(childSelect, 'unassigned');
    expect(screen.queryByText('Abby P')).toBeNull();
    expect(screen.getByText('Open')).toBeInTheDocument();
    await user.selectOptions(childSelect, '3');
    expect(screen.getByText('Abby P')).toBeInTheDocument();
  });

  it('renders AI suggestions when present', async () => {
    renderPage(buildUser(), [
      http.get('*/api/projects/', () => HttpResponse.json([])),
      http.get('*/api/projects/suggestions/', () =>
        HttpResponse.json([
          { title: 'Try this', description: 'desc', category: 'Science', difficulty: 3, estimated_hours: 2, why: 'because' },
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText(/try this/i)).toBeInTheDocument());
    expect(screen.getByText(/because/i)).toBeInTheDocument();
  });

  it('filters ventures by title via the search input', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/projects/', () =>
        HttpResponse.json([
          buildProject({ id: 1, title: 'Birdhouse', description: 'wooden box for finches' }),
          buildProject({ id: 2, title: 'Volcano', description: 'baking-soda eruption' }),
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('Birdhouse')).toBeInTheDocument());

    const search = screen.getByRole('searchbox', { name: /filter ventures/i });
    await user.type(search, 'volcano');

    expect(screen.queryByText('Birdhouse')).not.toBeInTheDocument();
    expect(screen.getByText('Volcano')).toBeInTheDocument();
  });

  it('hides the search input when there are no ventures', async () => {
    renderPage(buildUser(), [
      http.get('*/api/projects/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText(/no ventures yet/i)).toBeInTheDocument());
    expect(screen.queryByRole('searchbox', { name: /filter ventures/i })).toBeNull();
  });
});
