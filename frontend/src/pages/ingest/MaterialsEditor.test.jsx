import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MaterialsEditor from './MaterialsEditor.jsx';

describe('MaterialsEditor', () => {
  it('renders a list and fires add/update/remove', async () => {
    const onAdd = vi.fn();
    const onUpdate = vi.fn();
    const onRemove = vi.fn();
    const user = userEvent.setup();
    render(
      <MaterialsEditor
        materials={[{ name: 'Wood', estimated_cost: '5.00' }]}
        onAdd={onAdd} onUpdate={onUpdate} onRemove={onRemove}
      />,
    );
    expect(screen.getByDisplayValue('Wood')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /add/i }));
    expect(onAdd).toHaveBeenCalled();
    await user.type(screen.getByDisplayValue('Wood'), 'x');
    expect(onUpdate).toHaveBeenCalled();
    const removeBtn = screen.getAllByRole('button').find((b) => b.querySelector('svg')?.classList?.contains('lucide-trash2'));
    await user.click(removeBtn);
    expect(onRemove).toHaveBeenCalledWith(0);
  });
});
