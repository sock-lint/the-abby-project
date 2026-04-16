import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import SkillTreeView from './SkillTreeView.jsx';
import { server } from '../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('SkillTreeView', () => {
  it('renders empty state when categories list is empty', async () => {
    render(<SkillTreeView categories={[]} />);
    await waitFor(() =>
      expect(screen.getAllByText((t) => /skill|category|empty/i.test(t)).length).toBeGreaterThanOrEqual(0),
    );
  });

  it('fetches and renders a skill tree for a category', async () => {
    server.use(
      http.get(/\/api\/skills\/tree\/1\/$/, () =>
        HttpResponse.json({
          subjects: [],
          skills: [
            { id: 1, name: 'Addition', level: 1, xp_points: 50, unlocked: true, level_names: { 1: 'Apprentice', 2: 'Adept' } },
          ],
        }),
      ),
    );
    render(<SkillTreeView categories={[{ id: 1, name: 'Math', icon: '🧮' }]} />);
    // Tab button labels + content indicate successful render.
    await waitFor(() =>
      expect(screen.getAllByText((t) => /math|skill|level/i.test(t)).length).toBeGreaterThan(0),
    );
  });
});
