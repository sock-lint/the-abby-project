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
    expect(screen.getByRole('textbox', { name: 'Material 1 name' })).toHaveValue('Wood');
    expect(screen.getByRole('spinbutton', { name: 'Material 1 estimated cost' })).toHaveValue(5);
    await user.click(screen.getByRole('button', { name: /add/i }));
    expect(onAdd).toHaveBeenCalled();
    await user.type(screen.getByRole('textbox', { name: 'Material 1 name' }), 'x');
    expect(onUpdate).toHaveBeenCalledWith(0, { name: 'Woodx' });
    await user.click(screen.getByRole('button', { name: 'Remove material' }));
    expect(onRemove).toHaveBeenCalledWith(0);
  });
});
