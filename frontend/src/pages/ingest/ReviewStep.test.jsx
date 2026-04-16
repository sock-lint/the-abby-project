import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ReviewStep from './ReviewStep.jsx';

describe('ReviewStep', () => {
  it('renders a basic draft with no warnings', () => {
    render(
      <ReviewStep
        draft={{ title: 'x', description: '', milestones: [], steps: [], materials: [], resources: [] }}
        setDraft={vi.fn()}
        overrides={{ category_id: '', difficulty: 2, bonus_amount: '0', materials_budget: '0', due_date: '' }}
        setOverrides={vi.fn()}
        categories={[]}
        milestoneHandlers={{ add: vi.fn(), update: vi.fn(), remove: vi.fn() }}
        stepHandlers={{ add: vi.fn(), update: vi.fn(), remove: vi.fn() }}
        resourceHandlers={{ add: vi.fn(), update: vi.fn(), remove: vi.fn() }}
        materialHandlers={{ add: vi.fn(), update: vi.fn(), remove: vi.fn() }}
        committing={false}
        onCommit={vi.fn()}
        onDiscard={vi.fn()}
      />,
    );
    expect(screen.getAllByText(/milestones|steps|materials|resources|review/i).length).toBeGreaterThan(0);
  });

  it('renders warnings when present', () => {
    render(
      <ReviewStep
        draft={{
          title: 'x', description: '', milestones: [], steps: [], materials: [], resources: [],
          warnings: ['alpha'], pipeline_warnings: ['beta'],
        }}
        setDraft={vi.fn()}
        overrides={{}}
        setOverrides={vi.fn()}
        categories={[]}
        milestoneHandlers={{ add: vi.fn(), update: vi.fn(), remove: vi.fn() }}
        stepHandlers={{ add: vi.fn(), update: vi.fn(), remove: vi.fn() }}
        resourceHandlers={{ add: vi.fn(), update: vi.fn(), remove: vi.fn() }}
        materialHandlers={{ add: vi.fn(), update: vi.fn(), remove: vi.fn() }}
        committing={false}
        onCommit={vi.fn()}
        onDiscard={vi.fn()}
      />,
    );
    expect(screen.getByText(/alpha/)).toBeInTheDocument();
    expect(screen.getByText(/beta/)).toBeInTheDocument();
  });
});
