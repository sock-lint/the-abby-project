import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Achievements from './Achievements.jsx';
import { server } from '../test/server.js';
import { renderWithProviders } from '../test/render.jsx';
import { buildParent, buildUser } from '../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPage({ user = buildUser(), handlers = [] } = {}) {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(user)),
    ...handlers,
  );
  return renderWithProviders(<Achievements />);
}

describe('Achievements (Skills page)', () => {
  it('lets a parent switch modes with the shared arrow-key tab behavior', async () => {
    const user = userEvent.setup();
    renderPage({ user: buildParent(), handlers: [
      http.get('*/api/categories/', () => HttpResponse.json([])),
    ] });
    const view = await screen.findByRole('tab', { name: 'View' });
    view.focus();
    await user.keyboard('{ArrowRight}');
    expect(screen.getByRole('tab', { name: 'Manage' })).toHaveFocus();
    expect(screen.getByRole('tab', { name: 'Manage' })).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByRole('button', { name: /Categories/ })).toBeInTheDocument();
    await user.keyboard('{Home}');
    expect(view).toHaveFocus();
    expect(view).toHaveAttribute('aria-selected', 'true');
  });

  it('loads Wayfinder and skill details without requesting the achievements summary', async () => {
    const user = userEvent.setup();
    const summaryRequest = vi.fn(() => new HttpResponse('<!doctype html><title>Abby</title>', {
      status: 200,
      headers: { 'Content-Type': 'text/html' },
    }));
    renderPage({
      handlers: [
        http.get('*/api/achievements/summary/', summaryRequest),
        http.get('*/api/categories/', () =>
          HttpResponse.json([{ id: 1, name: 'Woodworking', icon: '🪵' }]),
        ),
        http.get('*/api/skills/tree/1/', () =>
          HttpResponse.json({
            category: { id: 1, name: 'Woodworking', icon: '🪵' },
            summary: { level: 1, total_xp: 150 },
            subjects: [{
              id: 10,
              name: 'Shop Basics',
              skills: [{ id: 100, name: 'Hand Tools', level: 1, xp_points: 150, unlocked: true }],
            }],
          }),
        ),
      ],
    });
    await user.click(await screen.findByRole('button', { name: /Woodworking/ }));
    await user.click(await screen.findByRole('button', { name: /Shop Basics/ }));
    await user.click(await screen.findByRole('button', { name: /^Hand Tools/ }));
    expect(await screen.findByRole('heading', { name: 'Hand Tools' })).toBeInTheDocument();
    expect(summaryRequest).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('retries a failed category request and never presents the failure as an empty catalog', async () => {
    const user = userEvent.setup();
    const summaryRequest = vi.fn(() => HttpResponse.json({ badges_earned: [] }));
    const categoryRequest = vi.fn(() => categoryRequest.mock.calls.length === 1
      ? HttpResponse.json({ error: 'Categories unavailable' }, { status: 500 })
      : HttpResponse.json([{ id: 1, name: 'Woodworking', icon: '🪵' }]));
    renderPage({ handlers: [
      http.get('*/api/achievements/summary/', summaryRequest),
      http.get('*/api/categories/', categoryRequest),
    ] });
    expect(await screen.findByRole('alert')).toHaveTextContent('Categories unavailable');
    expect(screen.queryByText(/no skill categories yet/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByRole('button', { name: /Woodworking/ })).toBeInTheDocument();
    expect(categoryRequest).toHaveBeenCalledTimes(2);
    expect(summaryRequest).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders the Skills header and skill tree for a child', async () => {
    renderPage({
      handlers: [
        http.get('*/api/categories/', () =>
          HttpResponse.json([{ id: 1, name: 'Woodworking', icon: '🪵' }]),
        ),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Skills' })).toBeInTheDocument(),
    );
    // Child should NOT see View | Manage toggle.
    expect(screen.queryByRole('tab', { name: 'Manage' })).toBeNull();
    expect(await screen.findByRole('button', { name: /Woodworking/ })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: /skill navigation/i })).toHaveTextContent('All skills');
  });

  it('opens a category on request and lets a child filter and inspect its skills', async () => {
    const user = userEvent.setup();
    renderPage({
      handlers: [
        http.get('*/api/categories/', () =>
          HttpResponse.json([{ id: 1, name: 'Woodworking', icon: '🪵' }]),
        ),
        http.get('*/api/skills/tree/1/', () =>
          HttpResponse.json({
            category: { id: 1, name: 'Woodworking', icon: '🪵' },
            summary: { level: 1, total_xp: 50 },
            subjects: [{
              id: 10,
              name: 'Advanced Technique',
              skills: [
                { id: 100, name: 'Mortise and Tenon', level: 1, xp_points: 10, unlocked: true },
                { id: 101, name: 'Dovetail', level: 0, xp_points: 0, unlocked: true },
              ],
            }],
            skills: [],
          }),
        ),
      ],
    });
    await user.click(await screen.findByRole('button', { name: /Woodworking/ }));
    expect(await screen.findByRole('button', { name: /Advanced Technique/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Mortise and Tenon/ })).not.toBeInTheDocument();

    const search = screen.getByRole('searchbox', { name: /filter skills/i });
    await user.type(search, 'dovetail');

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Mortise and Tenon/ })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Dovetail/ })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /Dovetail/ }));
    expect(await screen.findByRole('heading', { name: 'Dovetail' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: /skill navigation/i }))
      .toHaveTextContent(/All skills.*Woodworking.*Advanced Technique.*Dovetail/);
  });

  it('preserves the parent View | Manage toggle and returns to Wayfinder', async () => {
    const user = userEvent.setup();
    renderPage({
      user: buildParent(),
      handlers: [
        http.get('*/api/categories/', () => HttpResponse.json([])),
      ],
    });
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: 'Manage' })).toBeInTheDocument(),
    );
    expect(screen.getByRole('tab', { name: 'View' })).toHaveAttribute('aria-selected', 'true');
    await user.click(screen.getByRole('tab', { name: 'Manage' }));
    expect(await screen.findByRole('button', { name: /Categories/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Manage' })).toHaveAttribute('aria-selected', 'true');
    await user.click(screen.getByRole('tab', { name: 'View' }));
    expect(await screen.findByText(/no skill categories yet/i)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'View' })).toHaveAttribute('aria-selected', 'true');
  });
});
