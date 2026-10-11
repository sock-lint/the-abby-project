import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ResourcesEditor from './ResourcesEditor.jsx';

describe('ResourcesEditor', () => {
  it('renders resource rows and fires callbacks', async () => {
    const onAdd = vi.fn();
    const onUpdate = vi.fn();
    const onRemove = vi.fn();
    const user = userEvent.setup();
    render(
      <ResourcesEditor
        resources={[{ url: 'https://x', title: 'X' }]}
        steps={[{ title: 'A' }]}
        onAdd={onAdd}
        onUpdate={onUpdate}
        onRemove={onRemove}
      />,
    );
    expect(screen.getByRole('textbox', { name: 'Resource 1 URL' })).toHaveValue('https://x');
    expect(screen.getByRole('textbox', { name: 'Resource 1 title' })).toHaveValue('X');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Resource 1 type' }), 'video');
    expect(onUpdate).toHaveBeenCalledWith(0, { resource_type: 'video' });
    await user.selectOptions(screen.getByRole('combobox', { name: 'Resource 1 step' }), '0');
    expect(onUpdate).toHaveBeenCalledWith(0, { step_index: 0 });
    await user.click(screen.getByRole('button', { name: /add/i }));
    expect(onAdd).toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'Remove resource' }));
    expect(onRemove).toHaveBeenCalledWith(0);
  });
});
