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

beforeEach(() => {
  // jsdom doesn't implement scrollIntoView; stub so CategoryRibbon's effect
  // doesn't throw after activeId changes.
  Element.prototype.scrollIntoView = vi.fn();
});

describe('SkillTreeView', () => {
  it('renders an empty state when there are no categories', () => {
    render(<SkillTreeView categories={[]} />);
    expect(screen.getByText(/no skill categories yet/i)).toBeInTheDocument();
  });

  it('renders the category ribbon as a tablist with one tab per category', () => {
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
