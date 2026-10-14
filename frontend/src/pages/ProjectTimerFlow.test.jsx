import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import ProjectDetail from './ProjectDetail';
import ClockPage from './ClockPage';
import { AuthProvider } from '../hooks/useApi';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';
import { buildParent, buildProject, buildUser } from '../test/factories';
import { STORAGE_KEYS } from '../constants/storage';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');
  return { ...actual, AnimatePresence: ({ children }) => children };
});

function renderFlow({
  user = buildUser(), project = {}, initialEntry = '/quests/ventures/42',
  initialTimer = null, projectFailure = false, saveFailure = null,
} = {}) {
  let timer = initialTimer;
  const clock = spyHandler('post', '*/api/clock/', () => {
    if (saveFailure) return HttpResponse.json({ error: saveFailure }, { status: 400 });
    timer = { id: 8, status: 'active', project: 42, project_title: 'Selected project', clock_in: new Date().toISOString() };
    return timer;
  });
  localStorage.setItem(STORAGE_KEYS.LAST_CLOCK_PROJECT, '7');
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    http.get('*/api/projects/42/', () => projectFailure
      ? HttpResponse.json({ error: 'Project not found' }, { status: 404 })
      : HttpResponse.json(buildProject({ id: 42, title: 'Selected project', ...project }))),
    // The explicit project is absent from this page of the project list, and
    // remembered project 7 must never replace the intended project 42.
    http.get('*/api/projects/', () => HttpResponse.json({ count: 21, next: '/api/projects/?page=2', results: [buildProject({ id: 7, title: 'Remembered project' })] })),
    http.get('*/api/clock/', () => HttpResponse.json(timer)),
    http.get('*/api/time-entries/', () => HttpResponse.json([])),
    clock.handler,
  );
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <AuthProvider>
        <Routes>
          <Route path="/quests/ventures/:id" element={<ProjectDetail />} />
          <Route path="/clock" element={<ClockPage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
  return clock;
}

describe('Project timer flow', () => {
  it.each(['required', 'bounty'])('confirms the exact %s project before starting its timer', async (paymentKind) => {
    const user = userEvent.setup();
    const clock = renderFlow({ project: { payment_kind: paymentKind } });
    await user.click(await screen.findByRole('button', { name: 'Work on this project' }));
    expect(clock.calls).toHaveLength(0);
    expect(await screen.findByText('Clock in to work on Selected project.')).toBeInTheDocument();
    const start = screen.getByRole('button', { name: 'Clock in' });
    await user.click(start);
    await waitFor(() => expect(clock.calls).toHaveLength(1));
    expect(clock.calls[0].body).toEqual({ action: 'in', project_id: 42 });
    expect(clock.calls[0].url).toMatch(/\/api\/clock\/$/);
    expect(await screen.findByRole('button', { name: 'Clock out' })).toBeEnabled();
  });

  it.each([
    { name: 'a parent', user: buildParent(), project: {} },
    { name: 'a different child', user: buildUser({ id: 2 }), project: {} },
    ...['draft', 'in_review', 'completed', 'archived'].map((status) => ({ name: status, project: { status } })),
  ])('does not offer work from a project for $name', async ({ user, project }) => {
    const clock = renderFlow({ user, project });
    await screen.findByRole('heading', { name: 'Selected project' });
    expect(screen.queryByRole('button', { name: 'Work on this project' })).toBeNull();
    expect(clock.calls).toHaveLength(0);
  });

  it('offers work from an assigned project already in progress', async () => {
    renderFlow({ project: { status: 'in_progress' } });
    expect(await screen.findByRole('button', { name: 'Work on this project' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Submit for review' })).toBeInTheDocument();
  });

  it.each([7, 42])('keeps an existing timer on project %s without starting another', async (projectId) => {
    const user = userEvent.setup();
    const clock = renderFlow({ initialTimer: { status: 'active', project: projectId, project_title: 'Existing session', clock_in: new Date().toISOString() } });
    await user.click(await screen.findByRole('button', { name: 'Work on this project' }));
    expect(await screen.findByText('Existing session')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clock out' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Clock in' })).toBeNull();
    expect(clock.calls).toHaveLength(0);
  });

  it('requires an intentional choice to leave an invalid project target', async () => {
    const user = userEvent.setup();
    const clock = renderFlow({ initialEntry: '/clock?project=' });
    expect(await screen.findByRole('alert')).toHaveTextContent(/not available for you to work on/i);
    expect(screen.getByRole('button', { name: 'Clock in' })).toBeDisabled();
    expect(clock.calls).toHaveLength(0);
    await user.click(screen.getByRole('link', { name: 'Choose another project' }));
    const picker = await screen.findByRole('combobox', { name: 'Project' });
    await waitFor(() => expect(picker).toBeEnabled());
    expect(picker).toHaveValue('7');
    await user.click(screen.getByRole('button', { name: 'Clock in' }));
    await waitFor(() => expect(clock.calls).toHaveLength(1));
    expect(clock.calls[0].body).toEqual({ action: 'in', project_id: 7 });
    expect(clock.calls[0].url).toMatch(/\/api\/clock\/$/);
  });

  it('does not fall back to a remembered project when the requested project is missing', async () => {
    const user = userEvent.setup();
    const clock = renderFlow({ initialEntry: '/clock?project=42', projectFailure: true });
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/couldn't load the selected project/i);
    const start = screen.getByRole('button', { name: 'Clock in' });
    expect(start).toBeDisabled();
    await user.click(start);
    expect(clock.calls).toHaveLength(0);
    expect(screen.getByRole('link', { name: 'Choose another project' })).toHaveAttribute('href', '/clock');
  });

  it.each([
    { name: 'another child', project: { assigned_to: buildUser({ id: 2 }) } },
    { name: 'review status', project: { status: 'in_review' } },
  ])('blocks an explicit target for $name without using the remembered project', async ({ project }) => {
    const user = userEvent.setup();
    const clock = renderFlow({ initialEntry: '/clock?project=42', project });
    expect(await screen.findByRole('alert')).toHaveTextContent(/not available for you to work on/i);
    const start = screen.getByRole('button', { name: 'Clock in' });
    expect(start).toBeDisabled();
    await user.click(start);
    expect(clock.calls).toHaveLength(0);
  });

  it('keeps the chosen project when the server refuses clock-in during quiet hours', async () => {
    const user = userEvent.setup();
    const clock = renderFlow({ initialEntry: '/clock?project=42', saveFailure: 'Cannot clock in during quiet hours (22:00 - 7:00).' });
    expect(await screen.findByText('Clock in to work on Selected project.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Clock in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/quiet hours/i);
    expect(clock.calls).toHaveLength(1);
    expect(clock.calls[0].body).toEqual({ action: 'in', project_id: 42 });
    expect(clock.calls[0].url).toMatch(/\/api\/clock\/$/);
    expect(screen.getByText('Clock in to work on Selected project.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Clock out' })).toBeNull();
  });

  it('retries an unavailable selected project without changing the intended target', async () => {
    const user = userEvent.setup();
    const clock = renderFlow({ initialEntry: '/clock?project=42' });
    let unavailable = true;
    server.use(http.get('*/api/projects/42/', () => unavailable
      ? HttpResponse.json({ error: 'Project lookup unavailable' }, { status: 503 })
      : HttpResponse.json(buildProject({ id: 42, title: 'Selected project' }))));
    const alert = await screen.findByRole('alert');
    unavailable = false;
    await user.click(within(alert).getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Clock in to work on Selected project.')).toBeInTheDocument();
    expect(clock.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Clock in' }));
    await waitFor(() => expect(clock.calls).toHaveLength(1));
    expect(clock.calls[0].body).toEqual({ action: 'in', project_id: 42 });
  });
});
