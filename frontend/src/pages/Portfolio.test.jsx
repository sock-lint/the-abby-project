import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import Portfolio from './Portfolio.jsx';
import { server } from '../test/server.js';
import { spyHandler } from '../test/spy.js';
import { buildProject, buildUser, buildParent } from '../test/factories.js';
import { renderWithProviders, screen, waitFor } from '../test/render.jsx';
import { setToken } from '../api/client.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function mockAuth(user) {
  setToken('test-token');
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
  );
}

describe('Portfolio', () => {
  it('renders the empty state when nothing is uploaded', async () => {
    mockAuth(buildUser({ id: 1 }));
    server.use(
      http.get('*/api/portfolio/', () => HttpResponse.json({ projects: [], homework: [] })),
    );
    renderWithProviders(<Portfolio />);
    await waitFor(() => expect(screen.getByText(/no pages yet/i)).toBeInTheDocument());
  });

  it('renders project photos and download link', async () => {
    mockAuth(buildUser({ id: 1 }));
    server.use(
      http.get('*/api/portfolio/', () =>
        HttpResponse.json({
          projects: [
            {
              project_id: 1, project_title: 'Bird Feeder',
              photos: [{ id: 9, image: '/x.jpg', caption: 'front', user: 1, uploaded_at: '2026-04-10T00:00:00Z' }],
            },
          ],
          homework: [],
        }),
      ),
    );
    renderWithProviders(<Portfolio />);
    await waitFor(() => expect(screen.getByText('Bird Feeder')).toBeInTheDocument());
    expect(screen.getByText('front')).toBeInTheDocument();
    expect(screen.getByText(/download all/i)).toBeInTheDocument();
  });

  it('filter pills switch the visible set', async () => {
    mockAuth(buildUser({ id: 1 }));
    server.use(
      http.get('*/api/portfolio/', () =>
        HttpResponse.json({
          projects: [{
            project_id: 1, project_title: 'Proj1',
            photos: [{ id: 1, image: '/x.jpg', user: 1, uploaded_at: '2026-04-10T00:00:00Z' }],
          }],
          homework: [{
            subject: 'math',
            items: [{ id: 1, image: '/h.jpg', assignment_title: 'HW1', caption: null, user_id: 1, submitted_at: '2026-04-11T00:00:00Z' }],
          }],
        }),
      ),
    );
    const { user } = renderWithProviders(<Portfolio />);
    await waitFor(() => expect(screen.getByText('HW1')).toBeInTheDocument());
    await user.click(screen.getByRole('tab', { name: /^Projects/ }));
    expect(screen.queryByText('HW1')).toBeNull();
    await user.click(screen.getByRole('tab', { name: /^Homework/ }));
    expect(screen.queryByText('Proj1')).toBeNull();
  });

  it('switches to by-date grouping and shows month headers', async () => {
    mockAuth(buildUser({ id: 1 }));
    server.use(
      http.get('*/api/portfolio/', () =>
        HttpResponse.json({
          projects: [{
            project_id: 1, project_title: 'Proj1',
            photos: [
              { id: 1, image: '/a.jpg', user: 1, uploaded_at: '2026-03-15T12:00:00Z', caption: 'march' },
              { id: 2, image: '/b.jpg', user: 1, uploaded_at: '2026-04-15T12:00:00Z', caption: 'april' },
            ],
          }],
          homework: [],
        }),
      ),
    );
    const { user } = renderWithProviders(<Portfolio />);
    await waitFor(() => expect(screen.getByText('Proj1')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /by date/i }));
    await waitFor(() => expect(screen.getByText(/April 2026/)).toBeInTheDocument());
    expect(screen.getByText(/March 2026/)).toBeInTheDocument();
  });

  it('opens the lightbox when a tile is clicked', async () => {
    mockAuth(buildUser({ id: 1 }));
    server.use(
      http.get('*/api/portfolio/', () =>
        HttpResponse.json({
          projects: [{
            project_id: 1, project_title: 'Proj1',
            photos: [{ id: 9, image: '/x.jpg', caption: 'hello', user: 1, uploaded_at: '2026-04-10T00:00:00Z' }],
          }],
          homework: [],
        }),
      ),
    );
    const { user } = renderWithProviders(<Portfolio />);
    await waitFor(() => expect(screen.getByText('Proj1')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /View hello/ }));
    expect(screen.getByRole('dialog', { name: /photo viewer/i })).toBeInTheDocument();
  });

  it('deletes a photo after confirm', async () => {
    mockAuth(buildParent({ id: 99 }));
    server.use(
      http.get('*/api/portfolio/', () =>
        HttpResponse.json({
          projects: [{
            project_id: 1, project_title: 'Proj1',
            photos: [{ id: 42, image: '/x.jpg', caption: 'doomed', user: 1, uploaded_at: '2026-04-10T00:00:00Z' }],
          }],
          homework: [],
        }),
      ),
    );
    const spy = spyHandler('delete', /\/api\/photos\/42\/$/, { ok: true });
    server.use(spy.handler);
    const { user } = renderWithProviders(<Portfolio />);
    await waitFor(() => expect(screen.getByText('doomed')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /Delete doomed/ }));
    // ConfirmDialog appears
    await waitFor(() =>
      expect(screen.getByRole('alertdialog', { name: /remove from sketchbook/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /^Remove$/ }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/photos\/42\/$/);
  });

  it('deletes a homework proof via the homework-proofs endpoint', async () => {
    mockAuth(buildParent({ id: 99 }));
    server.use(
      http.get('*/api/portfolio/', () =>
        HttpResponse.json({
          projects: [],
          homework: [{
            subject: 'math',
            items: [{ id: 7, image: '/h.jpg', assignment_title: 'HW1', caption: 'doomed-proof', user_id: 1, submitted_at: '2026-04-11T00:00:00Z' }],
          }],
        }),
      ),
    );
    const spy = spyHandler('delete', /\/api\/homework-proofs\/7\/$/, { ok: true });
    server.use(spy.handler);
    const { user } = renderWithProviders(<Portfolio />);
    await waitFor(() => expect(screen.getByText('doomed-proof')).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: /Delete doomed-proof/ }));
    await waitFor(() =>
      expect(screen.getByRole('alertdialog')).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /^Remove$/ }));
    await waitFor(() => expect(spy.calls).toHaveLength(1));
    expect(spy.calls[0].url).toMatch(/\/api\/homework-proofs\/7\/$/);
  });

  it('hides delete button for photos a child does not own', async () => {
    mockAuth(buildUser({ id: 1, role: 'child' }));
    server.use(
      http.get('*/api/portfolio/', () =>
        HttpResponse.json({
          projects: [{
            project_id: 1, project_title: 'Proj1',
            photos: [
              { id: 1, image: '/mine.jpg', caption: 'mine', user: 1, uploaded_at: '2026-04-10T00:00:00Z' },
              { id: 2, image: '/theirs.jpg', caption: 'theirs', user: 2, uploaded_at: '2026-04-10T00:00:00Z' },
            ],
          }],
          homework: [],
        }),
      ),
    );
    renderWithProviders(<Portfolio />);
    await waitFor(() => expect(screen.getByText('mine')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /Delete mine/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Delete theirs/ })).toBeNull();
  });

  it('opens the upload sheet and guards against empty submit', async () => {
    mockAuth(buildUser({ id: 1 }));
    server.use(
      http.get('*/api/portfolio/', () => HttpResponse.json({ projects: [], homework: [] })),
      http.get('*/api/projects/', () =>
        HttpResponse.json([buildProject({ id: 7, title: 'Target' })]),
      ),
      http.post('*/api/photos/', () => HttpResponse.json({ ok: true })),
    );
    window.URL.createObjectURL = vi.fn(() => 'blob:preview');
    const { user } = renderWithProviders(<Portfolio />);
    await waitFor(() => expect(screen.getByText(/affix photo/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /affix photo/i }));
    await user.click(screen.getByRole('button', { name: /upload photo/i }));
    expect(screen.getByRole('button', { name: /upload photo/i })).toBeDisabled();
  });
});
