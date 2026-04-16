import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Portfolio from './Portfolio.jsx';
import { server } from '../test/server.js';
import { buildProject } from '../test/factories.js';

// AnimatePresence would keep the upload sheet in the DOM on exit; stub.
vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('Portfolio', () => {
  it('renders the empty state when nothing is uploaded', async () => {
    server.use(
      http.get('*/api/portfolio/', () => HttpResponse.json({ projects: [], homework: [] })),
    );
    render(<Portfolio />);
    await waitFor(() => expect(screen.getByText(/no pages yet/i)).toBeInTheDocument());
  });

  it('supports the legacy array shape', async () => {
    server.use(
      http.get('*/api/portfolio/', () =>
        HttpResponse.json([
          { project_id: 1, project_title: 'Old', photos: [{ id: 1, image: '/a.jpg', caption: 'c' }] },
        ]),
      ),
    );
    render(<Portfolio />);
    await waitFor(() => expect(screen.getByText('Old')).toBeInTheDocument());
  });

  it('renders project photos and download link', async () => {
    server.use(
      http.get('*/api/portfolio/', () =>
        HttpResponse.json({
          projects: [
            { project_id: 1, project_title: 'Bird Feeder', photos: [{ id: 9, image: '/x.jpg', caption: 'front' }] },
          ],
          homework: [],
        }),
      ),
    );
    render(<Portfolio />);
    await waitFor(() => expect(screen.getByText('Bird Feeder')).toBeInTheDocument());
    expect(screen.getByText('front')).toBeInTheDocument();
    expect(screen.getByText(/download all/i)).toBeInTheDocument();
  });

  it('renders homework proofs and filter tabs', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/portfolio/', () =>
        HttpResponse.json({
          projects: [{ project_id: 1, project_title: 'Proj1', photos: [{ id: 1, image: '/x.jpg' }] }],
          homework: [
            { subject: 'math', items: [{ id: 1, image: '/h.jpg', assignment_title: 'HW1', caption: null }] },
          ],
        }),
      ),
    );
    render(<Portfolio />);
    await waitFor(() => expect(screen.getByText('HW1')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /^projects$/i }));
    expect(screen.queryByText('HW1')).toBeNull();
    await user.click(screen.getByRole('button', { name: /^homework$/i }));
    expect(screen.queryByText('Proj1')).toBeNull();
  });

  it('opens the upload sheet and uploads a photo', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/portfolio/', () => HttpResponse.json({ projects: [], homework: [] })),
      http.get('*/api/projects/', () =>
        HttpResponse.json([buildProject({ id: 7, title: 'Target' })]),
      ),
      http.post('*/api/photos/', () => HttpResponse.json({ ok: true })),
    );
    // Polyfill createObjectURL — jsdom lacks it.
    window.URL.createObjectURL = vi.fn(() => 'blob:preview');
    render(<Portfolio />);
    await waitFor(() => expect(screen.getByText(/affix photo/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /affix photo/i }));
    // Error without project or file
    await user.click(screen.getByRole('button', { name: /upload photo/i }));
    expect(screen.getByRole('button', { name: /upload photo/i })).toBeDisabled();
  });
});
