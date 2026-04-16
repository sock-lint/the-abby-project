import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ResourcePill, StepCard } from './ProjectPlanItems.jsx';

describe('ResourcePill', () => {
  it('renders a link with the resource title', () => {
    render(<ResourcePill resource={{ url: 'https://x', title: 'Guide', resource_type: 'video' }} />);
    expect(screen.getByText('Guide')).toBeInTheDocument();
    expect(screen.getByRole('link').getAttribute('href')).toBe('https://x');
  });

  it('falls back to URL when no title', () => {
    render(<ResourcePill resource={{ url: 'https://x', resource_type: 'link' }} />);
    expect(screen.getByText('https://x')).toBeInTheDocument();
  });
});

describe('StepCard', () => {
  it('renders step title', () => {
    render(
      <StepCard
        step={{ id: 1, title: 'Cut', is_completed: false, resources: [] }}
        isParent={false}
        milestones={[]}
        onToggle={vi.fn()}
        onDelete={vi.fn()}
        onMove={vi.fn()}
        onAddResource={vi.fn()}
        onDeleteResource={vi.fn()}
      />,
    );
    expect(screen.getByText('Cut')).toBeInTheDocument();
  });
});
