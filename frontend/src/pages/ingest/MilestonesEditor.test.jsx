import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MilestonesEditor from './MilestonesEditor.jsx';

describe('MilestonesEditor', () => {
  it('renders and fires mutation callbacks', async () => {
    const onAdd = vi.fn();
    const onUpdate = vi.fn();
    const onRemove = vi.fn();
    const user = userEvent.setup();
    render(
      <MilestonesEditor
        milestones={[{ title: 'Design', bonus_amount: '5' }]}
        onAdd={onAdd} onUpdate={onUpdate} onRemove={onRemove}
      />,
    );
    expect(screen.getByDisplayValue('Design')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /add/i }));
    expect(onAdd).toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: /remove milestone/i }));
    expect(onRemove).toHaveBeenCalledWith(0);
  });
});
