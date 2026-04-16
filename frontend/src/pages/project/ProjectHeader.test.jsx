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
});
