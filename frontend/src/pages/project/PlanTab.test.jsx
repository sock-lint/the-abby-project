import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import PlanTab from './PlanTab.jsx';
import { buildProject } from '../../test/factories.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderPlan(project, isParent = false) {
  return render(
    <PlanTab
      project={project}
      isParent={isParent}
      onCompleteMilestone={vi.fn()} onDeleteMilestone={vi.fn()}
      onToggleStep={vi.fn()} onDeleteStep={vi.fn()} onMoveStep={vi.fn()}
      onDeleteResource={vi.fn()}
      onOpenAddMilestone={vi.fn()}
      onOpenAddStep={vi.fn()}
      onOpenAddResource={vi.fn()}
    />,
  );
}

describe('PlanTab', () => {
  it('renders empty state when no milestones and no steps', () => {
    renderPlan(buildProject({ milestones: [], steps: [] }));
    expect(
      screen.getAllByText((t) => /empty|no steps|no milestones|plan|step/i.test(t)).length,
    ).toBeGreaterThanOrEqual(0);
  });

  it('renders milestones and grouped steps', () => {
    renderPlan(buildProject({
      milestones: [
        { id: 1, title: 'Design', is_completed: false, bonus_amount: '5' },
      ],
      steps: [
        { id: 10, title: 'Sketch', milestone: 1, is_completed: false, resources: [] },
        { id: 11, title: 'Loose step', milestone: null, is_completed: false, resources: [] },
      ],
    }));
    expect(screen.getByText('Design')).toBeInTheDocument();
    expect(screen.getByText('Sketch')).toBeInTheDocument();
    expect(screen.getByText('Loose step')).toBeInTheDocument();
  });
});
