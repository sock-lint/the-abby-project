import { describe, expect, it, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SkillTreeView from './SkillTreeView.jsx';
import { server } from '../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

const STORAGE_KEY = 'atlas:skill-tree:active-category';

beforeEach(() => {
  // jsdom doesn't implement scrollIntoView; stub so TomeShelf's effect
  // doesn't throw after activeId changes.
  Element.prototype.scrollIntoView = vi.fn();
});

// The shelf now opens a tome on mount, so every case with categories needs
// a tree handler for the category it lands on.
function mockTree(id, name) {
  server.use(
    http.get(new RegExp(`/api/skills/tree/${id}/$`), () =>
      HttpResponse.json({
        category: { id, name, icon: '🧮' },
        summary: { level: 1, total_xp: 50 },
        subjects: [
          {
            id: 10,
            name: 'Arithmetic',
            icon: '➕',
            summary: { level: 1, total_xp: 50 },
            skills: [
              {
                id: 1,
                name: 'Addition',
                icon: '🔢',
                level: 1,
                xp_points: 50,
                unlocked: true,
                level_names: { 1: 'Apprentice', 2: 'Adept' },
                prerequisites: [],
              },
            ],
          },
        ],
      }),
    ),
  );
}

describe('SkillTreeView', () => {
  it('renders an empty state when there are no categories', () => {
    render(<SkillTreeView categories={[]} />);
    expect(screen.getByText(/no skill categories yet/i)).toBeInTheDocument();
  });

  it('renders the category ribbon as a tablist with one tab per category', () => {
    mockTree(1, 'Math');
    render(
      <SkillTreeView
        categories={[
          { id: 1, name: 'Math', icon: '🧮' },
          { id: 2, name: 'Writing', icon: '🪶' },
        ]}
      />,
    );
    expect(screen.getByRole('tablist', { name: /skill categories/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Math/ })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Writing/ })).toBeInTheDocument();
  });

  it('opens the first tome on mount instead of an empty "pull a tome" state', async () => {
    mockTree(1, 'Math');
    render(<SkillTreeView categories={[{ id: 1, name: 'Math', icon: '🧮' }]} />);

    await waitFor(() => expect(screen.getByText('Addition')).toBeInTheDocument());
    expect(screen.queryByText(/pull a tome from the shelf/i)).toBeNull();
    expect(screen.getByRole('tab', { name: /Math/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('keeps the folio open when the active spine is tapped again', async () => {
    mockTree(1, 'Math');
    const user = userEvent.setup();
    render(<SkillTreeView categories={[{ id: 1, name: 'Math', icon: '🧮' }]} />);
    await waitFor(() => expect(screen.getByText('Addition')).toBeInTheDocument());

    await user.click(screen.getByRole('tab', { name: /Math/ }));

    // Re-tapping used to toggle-deselect back to the empty state.
    await waitFor(() => expect(screen.getByText('Addition')).toBeInTheDocument());
    expect(screen.queryByText(/pull a tome from the shelf/i)).toBeNull();
  });

  it('restores the remembered category from localStorage', async () => {
    mockTree(2, 'Writing');
    window.localStorage.setItem(STORAGE_KEY, '2');
    render(
      <SkillTreeView
        categories={[
          { id: 1, name: 'Math', icon: '🧮' },
          { id: 2, name: 'Writing', icon: '🪶' },
        ]}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /Writing/ })).toHaveAttribute('aria-selected', 'true'),
    );
    expect(screen.getByRole('tab', { name: /Math/ })).toHaveAttribute('aria-selected', 'false');
  });

  it('remembers the category the user picked', async () => {
    mockTree(1, 'Math');
    mockTree(2, 'Writing');
    const user = userEvent.setup();
    render(
      <SkillTreeView
        categories={[
          { id: 1, name: 'Math', icon: '🧮' },
          { id: 2, name: 'Writing', icon: '🪶' },
        ]}
      />,
    );
    await user.click(screen.getByRole('tab', { name: /Writing/ }));
    await waitFor(() => expect(window.localStorage.getItem(STORAGE_KEY)).toBe('2'));
  });

  it('fetches and renders a skill tree when a pennant is clicked', async () => {
    server.use(
      http.get(/\/api\/skills\/tree\/1\/$/, () =>
        HttpResponse.json({
          category: { id: 1, name: 'Math', icon: '🧮' },
          summary: { level: 1, total_xp: 50 },
          subjects: [
            {
              id: 10,
              name: 'Arithmetic',
              icon: '➕',
              summary: { level: 1, total_xp: 50 },
              skills: [
                {
                  id: 1,
                  name: 'Addition',
                  icon: '🔢',
                  level: 1,
                  xp_points: 50,
                  unlocked: true,
                  level_names: { 1: 'Apprentice', 2: 'Adept' },
                  prerequisites: [],
                },
              ],
            },
          ],
        }),
      ),
    );
    const user = userEvent.setup();
    render(<SkillTreeView categories={[{ id: 1, name: 'Math', icon: '🧮' }]} />);
    await user.click(screen.getByRole('tab', { name: /Math/ }));
    await waitFor(() => expect(screen.getByText('Addition')).toBeInTheDocument());
    expect(screen.getByText('Arithmetic')).toBeInTheDocument();
    expect(screen.getByText('§I')).toBeInTheDocument();
  });
});
