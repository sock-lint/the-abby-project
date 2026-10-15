import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import StepsEditor from './StepsEditor.jsx';

describe('StepsEditor', () => {
  it('shows the no-steps note for empty list', () => {
    render(
      <StepsEditor steps={[]} milestones={[]} onAdd={vi.fn()} onUpdate={vi.fn()} onRemove={vi.fn()} />,
    );
    expect(screen.getByText(/no walkthrough/i)).toBeInTheDocument();
  });

  it('fires add/remove callbacks', async () => {
    const onAdd = vi.fn();
    const onRemove = vi.fn();
    const user = userEvent.setup();
    render(
      <StepsEditor
        steps={[{ title: 'Cut', description: '' }]}
        milestones={[{ title: 'Plan' }]}
        onAdd={onAdd}
        onUpdate={vi.fn()}
        onRemove={onRemove}
      />,
    );
    expect(screen.getByRole('textbox', { name: 'Step 1 title' })).toHaveValue('Cut');
    expect(screen.getByRole('textbox', { name: 'Step 1 description' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Step 1 milestone' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /add/i }));
    expect(onAdd).toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Remove step' }));
    expect(onRemove).toHaveBeenCalledWith(0);
  });
});
