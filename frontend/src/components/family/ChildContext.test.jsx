import { it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChildContext from './ChildContext';

it('names the viewed child and keeps selection and companion actions keyboard accessible', async () => {
  const select = vi.fn();
  render(<ChildContext children={[{ id: 7, display_name: 'Abby' }, { id: 8, username: 'ben' }]}
    selectedChildId={7} onSelect={select} actions={<button>Add memory</button>} />);
  const picker = screen.getByRole('combobox', { name: 'Viewing' });
  expect(picker).toHaveValue('7');
  const user = userEvent.setup();
  await user.selectOptions(picker, '8');
  expect(select).toHaveBeenCalledWith('8');
  expect(screen.getByRole('button', { name: 'Add memory' })).toBeInTheDocument();
});
