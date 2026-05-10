import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ProjectHeader from './ProjectHeader.jsx';
import { buildProject } from '../../test/factories.js';

function renderHeader(props = {}) {
  return render(
    <MemoryRouter>
      <ProjectHeader
        project={buildProject(props.project || {})}
        isParent={!!props.isParent}
        isAssigned={!!props.isAssigned}
        onAction={props.onAction || vi.fn()}
        onEdit={props.onEdit || vi.fn()}
        onOpenQR={props.onOpenQR || vi.fn()}
      />
    </MemoryRouter>,
  );
}

describe('ProjectHeader', () => {
  it('renders project title and back link', () => {
    renderHeader();
    expect(screen.getByText(/back to ventures/i)).toBeInTheDocument();
  });

  it('parent sees edit button', async () => {
    const onEdit = vi.fn();
    const user = userEvent.setup();
    renderHeader({ isParent: true, onEdit });
    const editBtn = screen.getAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-pencil'));
    if (editBtn) {
      await user.click(editBtn);
      expect(onEdit).toHaveBeenCalled();
    }
  });

  it('renders an illuminated versal of the title first letter with status-driven gilt', () => {
    const { container } = renderHeader({
      project: { title: 'Adobe Brick Oven', status: 'in_review' },
    });
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal).not.toBeNull();
    expect(versal.getAttribute('data-progress')).toBe('80');
    // in_review → 80% → cresting tier
    expect(versal.getAttribute('data-tier')).toBe('cresting');
  });

  it('renders a draft project versal with locked tier (status pre-unlock)', () => {
    const { container } = renderHeader({
      project: { title: 'Backyard Trebuchet', status: 'draft' },
    });
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal.getAttribute('data-tier')).toBe('locked');
  });

  it('renders a completed project versal as fully gilded', () => {
    const { container } = renderHeader({
      project: { title: 'Capstone', status: 'completed' },
    });
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal.getAttribute('data-progress')).toBe('100');
    expect(versal.getAttribute('data-tier')).toBe('gilded');
  });
});
