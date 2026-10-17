import { selectDropdown } from '../test/selectDropdown';
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
  it('shows ordinary projects without duplicating linked homework plans', async () => {
    renderPage(buildUser(), [
      http.get('*/api/projects/', () => HttpResponse.json([
        buildProject({ id: 12, title: 'Birdhouse' }),
        buildProject({ id: 13, title: 'Science homework plan', is_homework_plan: true }),
      ])),
    ]);
    expect(await screen.findByRole('button', { name: 'Open Birdhouse' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open Science homework plan' })).not.toBeInTheDocument();
  });

  it('exports only a dated saved project and keeps its calendar control separate from navigation', async () => {
    const user = userEvent.setup();
    renderPage(buildUser(), [
      http.get('*/api/projects/', () => HttpResponse.json([
        buildProject({ id: 12, title: 'Birdhouse', due_date: '2026-09-03' }),
        buildProject({ id: 13, title: 'Undated project', due_date: null }),
      ])),
    ]);
    const add = await screen.findByRole('button', { name: 'Add Project due: Birdhouse to calendar' });
    expect(screen.queryByRole('button', { name: 'Add Project due: Undated project to calendar' })).not.toBeInTheDocument();
    expect(add.parentElement.closest('button')).toBeNull();
    expect(screen.getByRole('button', { name: 'Open Birdhouse' })).toBeInTheDocument();
    await user.click(add);
    const google = screen.getByRole('link', { name: 'Google Calendar' });
    const event = new URL(google.href).searchParams;
    expect(event.get('text')).toBe('Project due: Birdhouse');
    expect(event.get('dates')).toBe('20260903/20260904');
    expect(event.get('details')).toContain('/quests/ventures/12');
    google.addEventListener('click', (e) => e.preventDefault());
    await user.click(google);
  });

  it('renders the empty state when there are no projects', async () => {
    renderPage(buildUser(), [
      http.get('*/api/projects/', () => HttpResponse.json([])),
    ]);
    await waitFor(() =>
      expect(screen.getByText(/no projects yet/i)).toBeInTheDocument(),
    );
  });

  it('shows a retry-able error instead of the empty state when the fetch fails', async () => {
    const user = userEvent.setup();
    let attempt = 0;
    renderPage(buildUser(), [
      http.get('*/api/projects/', () => {
        attempt += 1;
        return attempt === 1
          ? HttpResponse.json({ error: 'server exploded' }, { status: 500 })
          : HttpResponse.json([buildProject({ id: 1, title: 'Birdhouse' })]);
      }),
    ]);

    expect(await screen.findByRole('alert')).toHaveTextContent(/server exploded/i);
    // "No projects yet" would read as data loss on a flaky phone connection.
    expect(screen.queryByText(/no projects yet/i)).toBeNull();

    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByText('Birdhouse')).toBeInTheDocument();
  });

  it('shows "New project" only for parents', async () => {
    renderPage(buildParent(), [
      http.get('*/api/projects/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText(/new project/i)).toBeInTheDocument());
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
    expect(screen.getByText(/available to claim/i)).toBeInTheDocument();
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
    await selectDropdown(user, statusSelect, 'completed');
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
    await selectDropdown(user, typeSelect, 'bounty');
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
    await selectDropdown(user, childSelect, 'unassigned');
    expect(screen.queryByText('Abby P')).toBeNull();
    expect(screen.getByText('Open')).toBeInTheDocument();
    await selectDropdown(user, childSelect, '3');
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

  it('filters projects by title via the search input', async () => {
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

    const search = screen.getByRole('searchbox', { name: /filter projects/i });
    await user.type(search, 'volcano');

    expect(screen.queryByText('Birdhouse')).not.toBeInTheDocument();
    expect(screen.getByText('Volcano')).toBeInTheDocument();
  });

  it('hides the search input when there are no projects', async () => {
    renderPage(buildUser(), [
      http.get('*/api/projects/', () => HttpResponse.json([])),
    ]);
    await waitFor(() => expect(screen.getByText(/no projects yet/i)).toBeInTheDocument());
    expect(screen.queryByRole('searchbox', { name: /filter projects/i })).toBeNull();
  });

  it('renders the QuestFolio verso with title + tier + progress', async () => {
    const { container } = renderPage(buildUser(), [
      http.get('*/api/projects/', () =>
        HttpResponse.json([
          buildProject({ id: 1, title: 'Alpha', status: 'completed' }),
          buildProject({ id: 2, title: 'Beta',  status: 'in_progress' }),
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('Alpha')).toBeInTheDocument());
    const verso = container.querySelector('[data-folio-verso="true"]');
    expect(verso).not.toBeNull();
    // 1 of 2 completed → 50% progress → rising tier (≥ 25, < 60).
    expect(verso).toHaveAttribute('data-tier', 'rising');
    expect(verso).toHaveAttribute('data-progress', '50');
    // The verso renders the chapter title "Projects".
    expect(verso.textContent).toMatch(/Projects/);
    // RarityStrand paints per-rarity segments based on difficulty distribution.
    expect(container.querySelector('[data-rarity]')).not.toBeNull();
  });

  it('groups projects by status into ChapterRubric sections', async () => {
    renderPage(buildUser(), [
      http.get('*/api/projects/', () =>
        HttpResponse.json([
          buildProject({ id: 1, title: 'ActiveA', status: 'in_progress' }),
          buildProject({ id: 2, title: 'DoneA',   status: 'completed' }),
        ]),
      ),
    ]);
    await waitFor(() => expect(screen.getByText('ActiveA')).toBeInTheDocument());
    // Each rubric renders an h3 with the section name — the badges + filter
    // options reuse "In Progress" / "Completed" text elsewhere so role-scoped
    // queries pin the rubric specifically.
    expect(screen.getByRole('heading', { level: 3, name: /^In Progress$/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: /^Completed$/ })).toBeInTheDocument();
    expect(screen.getByText('DoneA')).toBeInTheDocument();
  });
});
